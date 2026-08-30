"""Qual encoder usar e com quais flags.

Separado do `ffmpeg.py` de propósito: lá mora "onde está o binário e do que ele
é capaz"; aqui mora "o que fazer com essa capacidade". Este módulo não abre
processo nenhum — recebe o conjunto de encoders disponíveis e decide. Isso o
torna verificável sem um ffmpeg na máquina, que é o que permite montar o comando
do Windows a partir do Mac (`send --dry-run`).

Duas coisas que a Fase 0 pagou caro para descobrir e que estão codificadas aqui:

* **Cada fabricante nomeia o preset do seu jeito.** NVENC usa `-preset p5`, o AMF
  usa `-quality quality`, o QSV usa `-preset medium` e o x264 usa
  `-preset veryfast`. Um `[video] preset` global só pode existir se souber para
  qual família está falando — por isso o default é vazio ("use o da família") e um
  valor explícito é conferido contra a lista da família escolhida.
* **Encoder de software precisa dos frames na RAM.** O `ddagrab` entrega frames
  D3D11 na GPU; o `libx264` não os enxerga. Só nesse caso entra
  `hwdownload,format=bgra,format=nv12` — e ele custa CPU, por isso não é default
  (baseline §2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Ordem = preferência. HEVC antes de H.264 em cada fabricante porque é ele que faz
# 1080p60 caber em 15 Mbps neste caminho de rede (PLANO §3.3) — requisito, não gosto.
ENCODER_CHAIN: tuple[str, ...] = (
    "hevc_nvenc",
    "h264_nvenc",
    "hevc_amf",
    "h264_amf",
    "hevc_qsv",
    "h264_qsv",
    "hevc_videotoolbox",
    "h264_videotoolbox",
    "libx265",
    "libx264",
)

# Qual encoder entrega qual codec. Não dá para deduzir do nome: `libx265` é HEVC
# e não começa com "hevc", e concluir o contrário faria o doctor dizer que o
# codec pedido não foi atendido quando foi.
CODEC_FAMILIES: dict[str, tuple[str, ...]] = {
    "hevc": ("hevc_nvenc", "hevc_amf", "hevc_qsv", "hevc_videotoolbox", "libx265"),
    "h264": ("h264_nvenc", "h264_amf", "h264_qsv", "h264_videotoolbox", "libx264"),
}

_HW_ENCODER_RE = re.compile(r"nvenc|_amf|_qsv|videotoolbox")


class EncoderError(Exception):
    """Escolha de encoder impossível — mensagem já pronta para o usuário final."""


@dataclass(frozen=True)
class Profile:
    """Como falar com uma família de encoders."""

    name: str
    preset_flag: str
    default_preset: str
    presets: tuple[str, ...]
    # Flags fixas da família, depois do `-c:v`. O controle de taxa (`-b:v`,
    # `-maxrate`, `-bufsize`) não está aqui: é igual para todos e vem do sender.
    extra: tuple[str, ...] = ()
    # O ddagrab entrega D3D11; encoder de software precisa dos frames na RAM.
    needs_hwdownload: bool = False


# `-tune hq` e `-rc cbr` no NVENC vêm do win-test-video.ps1 da Fase 0, e o `p5`
# saiu da varredura de presets do baseline (p1..p5 diferem em 1 fps; só o p7
# cobra caro). Os ramos AMF e QSV nunca rodaram — esta máquina não tem GPU AMD
# nem iGPU Intel —, então valem como fallback plausível, não como medido.
NVENC = Profile(
    name="nvenc",
    preset_flag="-preset",
    default_preset="p5",
    presets=("p1", "p2", "p3", "p4", "p5", "p6", "p7"),
    extra=("-tune", "hq", "-rc", "cbr"),
)
AMF = Profile(
    name="amf",
    preset_flag="-quality",
    default_preset="quality",
    presets=("speed", "balanced", "quality"),
    extra=("-rc", "cbr"),
)
QSV = Profile(
    name="qsv",
    preset_flag="-preset",
    default_preset="medium",
    presets=("veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"),
)
VIDEOTOOLBOX = Profile(
    name="videotoolbox",
    preset_flag="",
    default_preset="",
    presets=(),
    extra=("-realtime", "1"),
)
SOFTWARE = Profile(
    name="software",
    preset_flag="-preset",
    default_preset="veryfast",
    presets=(
        "ultrafast",
        "superfast",
        "veryfast",
        "faster",
        "fast",
        "medium",
        "slow",
        "slower",
        "veryslow",
        "placebo",
    ),
    extra=("-tune", "zerolatency"),
    needs_hwdownload=True,
)


def codec_of(encoder: str) -> str | None:
    """Codec que este encoder produz, ou None se for um nome desconhecido."""
    return next((codec for codec, names in CODEC_FAMILIES.items() if encoder in names), None)


def profile_of(encoder: str) -> Profile:
    """Família do encoder. Nome desconhecido cai no perfil de software.

    Cair no software é a escolha conservadora: ele é o único que não assume
    aceleração nenhuma, então um encoder novo (`av1_nvenc`, digamos) no máximo
    perde desempenho — não monta um comando que o ffmpeg recusa.
    """
    if encoder.endswith("_nvenc"):
        return NVENC
    if encoder.endswith("_amf"):
        return AMF
    if encoder.endswith("_qsv"):
        return QSV
    if encoder.endswith("_videotoolbox"):
        return VIDEOTOOLBOX
    return SOFTWARE


def hardware_encoders(available: set[str]) -> list[str]:
    return sorted(e for e in available if _HW_ENCODER_RE.search(e))


def pick(available: set[str], codec: str = "hevc", override: str = "") -> str:
    """Escolhe o encoder pela cadeia de fallback, preferindo o codec pedido.

    `available` vazio significa "não sei o que existe" — só acontece em
    `--dry-run` numa máquina que não é a que vai rodar. Aí o override manda e a
    cadeia devolve o primeiro da preferência, sem fingir que verificou.
    """
    if override:
        if available and override not in available:
            raise EncoderError(
                f"encoder {override!r} não existe neste ffmpeg.\n"
                f"  Disponíveis por hardware: "
                f"{', '.join(hardware_encoders(available)) or 'nenhum'}"
            )
        return override
    preferred = [e for e in ENCODER_CHAIN if e in CODEC_FAMILIES.get(codec, ())]
    ordered = preferred + [e for e in ENCODER_CHAIN if e not in preferred]
    if not available:
        return ordered[0]
    for candidate in ordered:
        if candidate in available:
            return candidate
    raise EncoderError("nenhum encoder de vídeo utilizável neste ffmpeg")


def preset_args(encoder: str, configured: str = "") -> list[str]:
    """`-preset p5`, `-quality quality`, ... conforme a família do encoder.

    Um preset explícito que não pertence à família escolhida é erro, não aviso:
    o ffmpeg aceitaria `-preset veryfast` num `hevc_nvenc` e cairia num default
    silencioso, e "por que a qualidade mudou" é exatamente o tipo de pergunta
    que este projeto existe para não precisar responder.
    """
    profile = profile_of(encoder)
    if not profile.preset_flag:
        if configured:
            raise EncoderError(
                f"[video] preset = {configured!r} — o encoder {encoder} não tem preset.\n"
                "  Deixe a chave vazia."
            )
        return []
    value = configured or profile.default_preset
    if configured and configured not in profile.presets:
        raise EncoderError(
            f"[video] preset = {configured!r} não vale para {encoder}.\n"
            f"  Valores da família {profile.name}: {', '.join(profile.presets)}\n"
            f"  Deixe a chave vazia para usar o default ({profile.default_preset})."
        )
    return [profile.preset_flag, value]
