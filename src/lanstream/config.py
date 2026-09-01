"""Carga e validação da config.

Ordem de busca (a primeira que existir vence, não há merge entre arquivos):

    1. o caminho passado em --config
    2. ./lanstream.toml            (raiz do projeto / cwd)
    3. ~/.config/lanstream/config.toml
    4. defaults embutidos

Chave ausente cai no default. Chave desconhecida ou com tipo errado é erro —
e erro aqui é `ConfigError` com mensagem legível, nunca stack trace: quem lê
está no meio de uma sessão de jogo, não depurando Python.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

CONFIG_FILENAME = "lanstream.toml"
USER_CONFIG = Path.home() / ".config" / "lanstream" / "config.toml"

CODECS = ("hevc", "h264")


class ConfigError(Exception):
    """Erro de configuração já formatado para o usuário final."""


# --------------------------------------------------------------------------- #
# Seções
# --------------------------------------------------------------------------- #


@dataclass
class NetworkConfig:
    # O IP do SENDER (o Windows), sempre — nas duas máquinas. É deste campo que
    # sai a URL de caller, e o caller só tem um destino possível. Preencher com o
    # IP local no Windows não é redundância: é o que o doctor confere para
    # detectar que o IP mudou antes de o Mac descobrir isso no meio da live.
    host: str = ""

    # A OUTRA ponta, do ponto de vista de quem roda. Só diagnóstico: é o alvo do
    # teste de alcance. No Mac não precisa (a outra ponta já é o `host`); no
    # Windows é o IP do Mac. Separado do `host` porque um campo com dois
    # significados não tem valor correto no Windows — achado da Fase 1
    # (`docs/fase1.md` §1).
    peer: str = ""
    port: int = 9000
    # Milissegundos. O ffmpeg e o OBS querem microssegundos na URL — a conversão
    # mora em url_for_ffmpeg()/url_for_srt_live_transmit(), num lugar só.
    latency_ms: int = 1200

    def validate(self) -> None:
        if not 1 <= self.port <= 65535:
            raise ConfigError(f"[network] port = {self.port} — fora da faixa 1..65535")
        if not 20 <= self.latency_ms <= 8000:
            raise ConfigError(
                f"[network] latency_ms = {self.latency_ms} — esperado entre 20 e 8000 ms.\n"
                "  Lembre que a unidade aqui é MILIssegundos (a Fase 0 usou 1200)."
            )

    def url_for_ffmpeg(self, *, mode: str, host: str | None = None) -> str:
        """URL SRT para ffmpeg e OBS — ambos passam pelo libavformat, que quer µs."""
        if mode not in ("listener", "caller"):
            raise ConfigError(f"modo SRT desconhecido: {mode!r}")
        addr = "0.0.0.0" if mode == "listener" else (host or self.host)
        if mode == "caller" and not addr:
            raise ConfigError(
                "[network] host está vazio — o lado que conecta precisa saber o IP do Windows.\n"
                "  Preencha host no lanstream.toml ou passe --host."
            )
        return f"srt://{addr}:{self.port}?mode={mode}&latency={self.latency_ms * 1000}"

    def url_for_srt_live_transmit(self, host: str | None = None) -> str:
        """O srt-live-transmit é a exceção: conta latência em MILIssegundos."""
        addr = host or self.host
        if not addr:
            raise ConfigError(
                "[network] host está vazio — o preview precisa saber o IP do Windows.\n"
                "  Preencha host no lanstream.toml ou passe --host."
            )
        return f"srt://{addr}:{self.port}?mode=caller&latency={self.latency_ms}"


@dataclass
class VideoConfig:
    width: int = 1920
    height: int = 1080
    fps: int = 60
    bitrate: str | int = "15M"
    codec: str = "hevc"
    encoder: str = ""
    monitor: int = 0

    # Vazio = o default da família do encoder escolhido (p5 no NVENC, "quality"
    # no AMF, "veryfast" no x264). Não dá para ter um default global: cada
    # fabricante nomeia o preset do seu jeito, e "p5" num libx264 é um erro. Quem
    # valida o valor contra a família é o encoders.preset_args().
    preset: str = ""

    def validate(self) -> None:
        if self.codec not in CODECS:
            raise ConfigError(
                f"[video] codec = {self.codec!r} — esperado um de {', '.join(CODECS)}"
            )
        if not 1 <= self.fps <= 240:
            raise ConfigError(f"[video] fps = {self.fps} — fora da faixa 1..240")
        for name in ("width", "height"):
            if getattr(self, name) <= 0:
                raise ConfigError(f"[video] {name} = {getattr(self, name)} — precisa ser positivo")
        if self.monitor < 0:
            raise ConfigError(f"[video] monitor = {self.monitor} — precisa ser >= 0")
        parse_bitrate(self.bitrate, "[video] bitrate")

    @property
    def gop(self) -> int:
        """Keyframe a cada 2 s, como o win-test-video.ps1 da Fase 0."""
        return self.fps * 2


@dataclass
class AudioConfig:
    enabled: bool = False
    device: str = ""
    bitrate: str | int = "160k"

    # Buffer do device dshow, em milissegundos. O default do ffmpeg é o do
    # device — "tipicamente algum múltiplo de 500 ms", diz a documentação —, e
    # meio segundo de áudio atrasado é o A/V sync inteiro da Fase 3 perdido de
    # graça. 50 ms é o valor conservador que a prática recomenda: baixo o
    # suficiente para não dominar o offset, alto o suficiente para não picotar.
    buffer_ms: int = 50

    # Correção de sincronismo, em milissegundos. POSITIVO ATRASA O ÁUDIO. Vira
    # `-itsoffset` na entrada do dshow. O valor não se adivinha: mede-se com o
    # scripts/av-sync.py, que imprime a linha pronta para colar aqui.
    #
    # Corrige um deslocamento CONSTANTE. Não corrige rampa: se o áudio se afasta
    # do vídeo com o tempo, o problema é de relógio e quem resolve é o `resync`.
    offset_ms: int = 0

    # Teto da fila de captura do dshow (`-rtbufsize`), em milissegundos de áudio.
    #
    # Existe por causa de um defeito medido em 01/09 (docs/fase5.md §5): o device
    # dshow abre quando o processo sobe, mas o listener SRT trava o ffmpeg até o
    # OBS conectar. O áudio capturado nessa espera vira fila, e a fila NUNCA
    # drena — depois da conexão o consumo é igual à produção, tempo real. O
    # backlog formado na espera vira atraso fixo do áudio pelo resto da execução.
    #
    # Com o default do ffmpeg (3.041.280 bytes = 15,8 s de áudio a 48 kHz
    # estéreo s16) os dois regimes medidos foram:
    #     espera <  15,8 s  ->  áudio limpo, atrasado pelo tempo da espera
    #     espera >  15,8 s  ->  satura: picote contínuo + ~15,8 s de atraso
    # Uma espera de 36 s deu 5325 quadros descartados em 16 minutos, com o vídeo
    # em 60 fps cravados e `speed=1x` o tempo todo — nenhum indicador acusa.
    #
    # O teto resolve porque descartar áudio ENQUANTO NINGUÉM ASSISTE não custa
    # nada: o que importa é que a conexão comece com áudio fresco. 500 ms é folga
    # confortável sobre o `buffer_ms` do device sem virar atraso audível.
    rtbuffer_ms: int = 500

    # Reamostra o áudio para mantê-lo colado na linha de tempo (`aresample=async`).
    # Ligado por default por causa do que a rodada de 31/08 mediu: o OBS acusou o
    # áudio 2204 ms e 2490 ms atrasado, duas vezes, em conexões de ~45 min, e
    # reiniciou a fonte sozinho. Isso é o relógio do device de captura correndo
    # diferente do relógio da captura de vídeo — dessincronia que cresce, e que
    # nenhum `offset_ms` alcança porque ele é uma constante.
    #
    # O custo é o áudio ser esticado ou comprimido em frações de milissegundo por
    # segundo, inaudível. Desligue só para medir a deriva crua (docs/fase3.md §12).
    resync: bool = True

    def validate(self) -> None:
        parse_bitrate(self.bitrate, "[audio] bitrate")
        if self.enabled and not self.device:
            raise ConfigError(
                "[audio] enabled = true mas device está vazio.\n"
                "  Liste os devices no Windows com:\n"
                "    lanstream doctor --audio"
            )
        # O `audio=` é do ffmpeg, não do nome: com ele o comando sairia
        # `-i audio=audio=CABLE Output` e o dshow diria só "I/O error", que não
        # aponta para nada. É engano provável — a documentação do ffmpeg mostra
        # o device sempre com o prefixo colado.
        if self.device.startswith(("audio=", "video=")):
            prefix, _, rest = self.device.partition("=")
            raise ConfigError(
                f"[audio] device = {self.device!r} — tire o '{prefix}=', é o lanstream que o põe.\n"
                f'  device = "{rest}"'
            )
        if '"' in self.device:
            raise ConfigError(
                f"[audio] device = {self.device!r} — aspas dentro do nome não passam pelo shell.\n"
                "  Use o nome como o `lanstream doctor --audio` imprime."
            )
        if not 10 <= self.buffer_ms <= 1000:
            raise ConfigError(
                f"[audio] buffer_ms = {self.buffer_ms} — esperado entre 10 e 1000 ms.\n"
                "  Abaixo de 10 o device picota; acima de 1000 o áudio atrasa mais que o SRT."
            )
        if not 50 <= self.rtbuffer_ms <= 20000:
            raise ConfigError(
                f"[audio] rtbuffer_ms = {self.rtbuffer_ms} — esperado entre 50 e 20000 ms.\n"
                "  Abaixo de 50 a fila descarta em operação normal, não só na espera;\n"
                "  acima de 20000 já passa do default do ffmpeg e não limita nada."
            )
        if self.rtbuffer_ms < self.buffer_ms:
            raise ConfigError(
                f"[audio] rtbuffer_ms = {self.rtbuffer_ms} é menor que "
                f"buffer_ms = {self.buffer_ms}.\n"
                "  A fila não pode ser menor que um bloco do device: ela descartaria\n"
                "  cada bloco assim que ele chegasse."
            )
        if not -2000 <= self.offset_ms <= 2000:
            raise ConfigError(
                f"[audio] offset_ms = {self.offset_ms} — esperado entre -2000 e 2000 ms.\n"
                "  Um valor maior que isso não é dessincronia, é outro defeito."
            )


@dataclass
class LogsConfig:
    # Vazio = `logs/` ao lado de onde se roda. O diretório já é ignorado pelo git.
    dir: str = ""
    max_mb: int = 5
    manter: int = 5
    # A linha de progresso do ffmpeg se reescreve várias vezes por segundo; no
    # arquivo ela entra por amostragem, senão a rotação descartaria as linhas de
    # erro, que são as raras e as que explicam.
    batimento_s: int = 30

    def validate(self) -> None:
        if not 1 <= self.max_mb <= 500:
            raise ConfigError(f"[logs] max_mb = {self.max_mb} — esperado entre 1 e 500")
        if not 1 <= self.manter <= 50:
            raise ConfigError(f"[logs] manter = {self.manter} — esperado entre 1 e 50")
        if not 1 <= self.batimento_s <= 3600:
            raise ConfigError(
                f"[logs] batimento_s = {self.batimento_s} — esperado entre 1 e 3600 s"
            )


@dataclass
class PathsConfig:
    ffmpeg: str = ""
    ffplay: str = ""
    srt_live_transmit: str = ""

    def validate(self) -> None:
        for f in fields(self):
            value = getattr(self, f.name)
            if value and not Path(value).exists():
                raise ConfigError(
                    f"[paths] {f.name} = {value!r} — esse arquivo não existe.\n"
                    "  Deixe a chave vazia para procurar no PATH."
                )


@dataclass
class Config:
    network: NetworkConfig = field(default_factory=NetworkConfig)
    video: VideoConfig = field(default_factory=VideoConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    logs: LogsConfig = field(default_factory=LogsConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)

    # De onde veio. None = só defaults.
    source: Path | None = None

    def validate(self) -> None:
        self.network.validate()
        self.video.validate()
        self.audio.validate()
        self.logs.validate()
        self.paths.validate()


SECTIONS: dict[str, type] = {
    "network": NetworkConfig,
    "video": VideoConfig,
    "audio": AudioConfig,
    "logs": LogsConfig,
    "paths": PathsConfig,
}


# --------------------------------------------------------------------------- #
# Utilitários
# --------------------------------------------------------------------------- #


def parse_bitrate(value: str | int, where: str) -> int:
    """ "15M" -> 15_000_000. Aceita o mesmo sufixo que o ffmpeg (K/M, sem case)."""
    # `bool` é subclasse de `int`: sem esta linha, bitrate = true viraria 1 bit/s.
    if isinstance(value, bool):
        raise ConfigError(
            f'{where} = {str(value).lower()} — esperado algo como "15M", não true/false'
        )
    if isinstance(value, int):
        if value <= 0:
            raise ConfigError(f"{where} = {value} — precisa ser positivo")
        return value
    if not isinstance(value, str):
        raise ConfigError(f'{where} = {value!r} — esperado algo como "15M" ou "160k"')
    text = value.strip()
    if not text:
        raise ConfigError(f'{where} está vazio — esperado algo como "15M" ou "160k"')
    multiplier = 1
    if text[-1] in "kK":
        multiplier, text = 1_000, text[:-1]
    elif text[-1] in "mM":
        multiplier, text = 1_000_000, text[:-1]
    try:
        number = float(text)
    except ValueError:
        raise ConfigError(
            f'{where} = {value!r} — não entendi. Use "15M", "20000k" ou um número em bits/s.'
        ) from None
    if number <= 0:
        raise ConfigError(f"{where} = {value!r} — precisa ser positivo")
    return int(number * multiplier)


def _did_you_mean(unknown: str, known: list[str]) -> str:
    import difflib

    match = difflib.get_close_matches(unknown, known, n=1, cutoff=0.6)
    return f" Você quis dizer {match[0]!r}?" if match else ""


def _build_section(name: str, cls: type, raw: Any, path: Path) -> Any:
    if not isinstance(raw, dict):
        raise ConfigError(
            f"{path}: [{name}] deveria ser uma seção (tabela TOML), não {type(raw).__name__}"
        )

    known = {f.name: f for f in fields(cls)}
    kwargs: dict[str, Any] = {}
    for key, value in raw.items():
        if key not in known:
            raise ConfigError(
                f"{path}: chave desconhecida [{name}] {key!r}.{_did_you_mean(key, list(known))}\n"
                f"  Chaves válidas: {', '.join(known)}"
            )
        expected = known[key].type
        if expected == "str | int":
            # Só o bitrate: "15M" e 15000000 são ambos válidos, e quem valida o
            # conteúdo é o parse_bitrate, com mensagem melhor do que a daqui.
            kwargs[key] = value
            continue
        # `bool` é subclasse de `int` em Python; sem esta checagem, port = true passaria.
        if expected == "int" and (not isinstance(value, int) or isinstance(value, bool)):
            raise ConfigError(f"{path}: [{name}] {key} = {value!r} — esperado um número inteiro")
        if expected == "str" and not isinstance(value, str):
            raise ConfigError(f"{path}: [{name}] {key} = {value!r} — esperado texto entre aspas")
        if expected == "bool" and not isinstance(value, bool):
            raise ConfigError(f"{path}: [{name}] {key} = {value!r} — esperado true ou false")
        kwargs[key] = value
    return cls(**kwargs)


def find_config_file(explicit: Path | None = None) -> Path | None:
    """Primeiro arquivo da cadeia de busca que existir."""
    if explicit is not None:
        if not explicit.exists():
            raise ConfigError(f"config não encontrada: {explicit}")
        return explicit
    for candidate in (Path.cwd() / CONFIG_FILENAME, USER_CONFIG):
        if candidate.exists():
            return candidate
    return None


def load(explicit: Path | None = None) -> Config:
    """Carrega, valida e devolve a config efetiva. Levanta ConfigError, nunca stack trace."""
    path = find_config_file(explicit)
    if path is None:
        cfg = Config()
        cfg.validate()
        return cfg

    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: TOML inválido — {exc}") from None
    except OSError as exc:
        raise ConfigError(f"não consegui ler {path}: {exc.strerror}") from None

    for key in raw:
        if key not in SECTIONS:
            raise ConfigError(
                f"{path}: seção desconhecida [{key}].{_did_you_mean(key, list(SECTIONS))}\n"
                f"  Seções válidas: {', '.join('[' + s + ']' for s in SECTIONS)}"
            )

    cfg = Config(
        **{
            name: _build_section(name, cls, raw.get(name, {}), path)
            for name, cls in SECTIONS.items()
        },
        source=path,
    )
    cfg.validate()
    return cfg
