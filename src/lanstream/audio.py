"""Áudio do jogo: qual device capturar no Windows e como muxá-lo no vídeo.

O ffmpeg **não tem** captura WASAPI loopback nativa no Windows. O que existe é o
DirectShow (`-f dshow`), e o dshow só enxerga *devices de captura* — ou seja,
alguém precisa expor a saída do sistema como se fosse um microfone. Quem faz isso
é o Stereo Mix da placa onboard, ou um driver virtual (VB-CABLE, VoiceMeeter,
`virtual-audio-capturer`). A escolha entre eles é do Windows e está argumentada em
`docs/fase3.md` §1; daqui para baixo o problema é só "o nome do device e as flags".

Como o `encoders.py`, este módulo **não abre processo** para decidir nada: recebe
texto e config, devolve argv. O único ponto que fala com o ffmpeg é o
`list_devices()`, e ele é chamado só pelo doctor.

Duas coisas custam caro se ficarem implícitas, então estão escritas aqui:

* **`-audio_buffer_size`.** O default do dshow é o do device, "tipicamente algum
  múltiplo de 500 ms" (docs do ffmpeg). Meio segundo de áudio atrasado em relação
  ao vídeo não é um detalhe de latência: é o A/V sync inteiro da Fase 3. Por isso
  o valor é explícito, e o default aqui é 50 ms.
* **`-thread_queue_size`.** Com duas entradas ao vivo no mesmo comando, a que for
  lida mais devagar enche a fila e o ffmpeg avisa
  ("Thread message queue blocking; consider raising the thread_queue_size option")
  — e, pior que o aviso, descarta pacote. É barato e é o padrão para captura dupla.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import AudioConfig, parse_bitrate

# Pacotes de fila por entrada. 1024 é o valor que a documentação do ffmpeg sugere
# quando o aviso aparece; a fila só ocupa memória se for usada.
THREAD_QUEUE = 1024

# O comando que lista os devices. Sai com código 1 e
# "dummy: Immediate exit requested" — isso é sucesso, não falha.
LIST_ARGS = ("-list_devices", "true", "-f", "dshow", "-i", "dummy")

# Nomes que denunciam um device de LOOPBACK (o que toca, capturado de volta) e
# não um microfone. Minúsculas, sem acento — a comparação normaliza os dois lados.
# O pt-BR entra porque o Windows desta máquina está em português e o Realtek
# traduz o Stereo Mix; procurar só o nome em inglês esconderia o device de graça.
_LOOPBACK_HINTS = (
    "stereo mix",
    "mixagem estereo",
    "mistura estereo",
    "what u hear",
    "wave out mix",
    "cable output",
    "voicemeeter out",
    "virtual-audio-capturer",
    "loopback",
)

_MIC_HINTS = ("microfone", "microphone", "headset", "webcam", "line in", "entrada de linha")

_PREFIX_RE = re.compile(r"^\[[a-z0-9_]+ @ [0-9a-fx]+\]\s*", re.IGNORECASE)
_DEVICE_RE = re.compile(r'^"(?P<name>.*)"(?:\s*\((?P<kind>audio|video)\))?$')
_ALT_RE = re.compile(r'^Alternative name\s+"(?P<alt>.*)"$')
_SECTION_RE = re.compile(r"^DirectShow (?P<kind>audio|video) devices", re.IGNORECASE)


class AudioError(Exception):
    """Problema de áudio já formatado para o usuário final."""


def _fold(text: str) -> str:
    """Minúsculas e sem acento, para comparar nome de device sem depender do idioma."""
    import unicodedata

    stripped = unicodedata.normalize("NFD", text.casefold())
    return "".join(c for c in stripped if unicodedata.category(c) != "Mn")


@dataclass(frozen=True)
class Device:
    """Um device DirectShow, como o ffmpeg o lista."""

    name: str
    kind: str = "audio"
    alternative: str = ""

    @property
    def role(self) -> str:
        """'loopback', 'microfone' ou 'desconhecido' — palpite pelo nome, nada mais.

        É palpite de propósito: o dshow não diz se um device é loopback, e o que
        decide de verdade é ouvir o resultado. Serve para ordenar a lista do
        `doctor --audio` e para o erro de device ausente sugerir o candidato certo.
        """
        folded = _fold(self.name)
        if any(hint in folded for hint in _LOOPBACK_HINTS):
            return "loopback"
        if any(hint in folded for hint in _MIC_HINTS):
            return "microfone"
        return "desconhecido"


def parse_devices(output: str) -> list[Device]:
    """Lê a saída de `-list_devices true`. Aguenta os dois formatos que existem.

    Até o ffmpeg 4.4 a listagem vinha em seções ("DirectShow audio devices" e
    depois os nomes); dos 5.x em diante cada linha traz o tipo no fim
    (`"Microfone (Realtek)" (audio)`). Um parser que só entendesse um dos dois
    diria "nenhum device de áudio" numa máquina cheia deles — o mesmo erro que o
    commit aacb863 consertou no `-encoders`, e por isso aqui os dois valem: a
    marca da linha ganha da seção quando as duas existem.
    """
    devices: list[Device] = []
    section = ""
    for raw in output.splitlines():
        line = _PREFIX_RE.sub("", raw).strip()
        if not line:
            continue
        found = _SECTION_RE.match(line)
        if found:
            section = found.group("kind").lower()
            continue
        alt = _ALT_RE.match(line)
        if alt and devices:
            # O nome alternativo (`@device_cm_{...}`) pertence ao device anterior.
            # Ele é o identificador estável: sobrevive a dois devices com o mesmo
            # rótulo, que é o caso de duas placas iguais na mesma máquina.
            devices[-1] = Device(devices[-1].name, devices[-1].kind, alt.group("alt"))
            continue
        device = _DEVICE_RE.match(line)
        if device:
            devices.append(Device(device.group("name"), device.group("kind") or section or "?"))
    return devices


def audio_devices(devices: list[Device]) -> list[Device]:
    """Só os de áudio, loopback primeiro — que é a ordem em que se quer lê-los."""
    order = {"loopback": 0, "desconhecido": 1, "microfone": 2}
    return sorted(
        (d for d in devices if d.kind in ("audio", "?")), key=lambda d: (order[d.role], d.name)
    )


def list_devices(info) -> list[Device]:
    """Pergunta ao ffmpeg quais devices dshow existem. Só faz sentido no Windows."""
    return parse_devices(info.raw(*LIST_ARGS))


def find(devices: list[Device], name: str) -> Device | None:
    """Device pelo nome exato; se não houver, tenta ignorando caixa e acento.

    O casamento tolerante existe para a mensagem de erro, não para o comando: o
    dshow abre o device pelo nome literal, então quem digitou "cable output"
    precisa ver o "CABLE Output" para copiar. Quem chama distingue os dois casos
    comparando `device.name` com o que pediu.
    """
    for device in devices:
        if device.name == name:
            return device
    folded = _fold(name)
    return next((d for d in devices if _fold(d.name) == folded), None)


# --------------------------------------------------------------------------- #
# argv
# --------------------------------------------------------------------------- #


def input_args(cfg: AudioConfig) -> list[str]:
    """O bloco de entrada do áudio: tudo isto vem ANTES do `-i` a que se aplica.

    Ordem importa duas vezes aqui. `-f dshow` primeiro porque `-audio_buffer_size`
    é opção privada do demuxer dshow — sem o formato declarado, o ffmpeg não sabe
    de quem é a opção. E o `-itsoffset` precisa estar neste bloco, não no de saída:
    como opção de entrada ele desloca os timestamps *deste* input, que é o que
    corrige o áudio contra o vídeo.
    """
    args = [
        "-f",
        "dshow",
        "-audio_buffer_size",
        str(cfg.buffer_ms),
        "-thread_queue_size",
        str(THREAD_QUEUE),
    ]
    if cfg.offset_ms:
        # Positivo ATRASA o áudio: o ffmpeg soma o offset aos timestamps da
        # entrada, e timestamp maior é apresentação mais tarde. Quem mede o valor
        # é o scripts/av-sync.py, que já imprime com o sinal certo.
        args += ["-itsoffset", f"{cfg.offset_ms / 1000:.3f}"]
    return [*args, "-i", f"audio={cfg.device}"]


def encode_args(cfg: AudioConfig) -> list[str]:
    """AAC, 48 kHz, estéreo.

    As três coisas são fixadas de propósito. 48 kHz porque é o que o MPEG-TS e o
    OBS esperam e o que evita um resample surpresa no meio do caminho; estéreo
    porque um device mono (um Stereo Mix mal configurado, um cabo virtual de um
    canal) sairia mono do outro lado e a descoberta seria na live; AAC porque é o
    que a Twitch aceita e o que o OBS repassa sem recodificar.
    """
    return [
        "-c:a",
        "aac",
        "-b:a",
        str(cfg.bitrate),
        "-ar",
        "48000",
        "-ac",
        "2",
    ]


def summary(cfg: AudioConfig) -> str:
    """A linha do `send` que responde 'o que vai de áudio'."""
    kbps = parse_bitrate(cfg.bitrate, "[audio] bitrate") // 1000
    offset = f", offset {cfg.offset_ms:+d} ms" if cfg.offset_ms else ""
    return f'aac {kbps}k 48kHz estéreo — dshow "{cfg.device}" (buffer {cfg.buffer_ms} ms{offset})'
