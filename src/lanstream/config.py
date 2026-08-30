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
    preset: str = "p5"

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

    def validate(self) -> None:
        parse_bitrate(self.bitrate, "[audio] bitrate")
        if self.enabled and not self.device:
            raise ConfigError(
                "[audio] enabled = true mas device está vazio.\n"
                "  Liste os devices no Windows com:\n"
                "    ffmpeg -list_devices true -f dshow -i dummy"
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
    paths: PathsConfig = field(default_factory=PathsConfig)

    # De onde veio. None = só defaults.
    source: Path | None = None

    def validate(self) -> None:
        self.network.validate()
        self.video.validate()
        self.audio.validate()
        self.paths.validate()


SECTIONS: dict[str, type] = {
    "network": NetworkConfig,
    "video": VideoConfig,
    "audio": AudioConfig,
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
