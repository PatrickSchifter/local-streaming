"""`lanstream doctor` — o diagnóstico que a Fase 0 fazia à mão.

Porta a lógica do `scripts/win-doctor.ps1` e a estende para o Mac. A regra é que
cada checagem responda a uma pergunta que já custou tempo neste projeto, e que a
mensagem de falha diga o comando que conserta. Checagem sem ação associada é ruído.

Convenção de saída: OK / AVISO / FALHA. O código de saída é 1 se houve FALHA —
assim dá para usar num script antes de subir o sender.
"""

from __future__ import annotations

import platform
import re
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum

import typer

from . import encoders as enc
from . import ffmpeg as ff
from .config import Config


class Level(Enum):
    OK = "OK"
    WARN = "AVISO"
    FAIL = "FALHA"


_STYLE = {Level.OK: "green", Level.WARN: "yellow", Level.FAIL: "red"}


@dataclass
class Check:
    level: Level
    label: str
    detail: str = ""
    hint: str = ""


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)

    def add(self, level: Level, label: str, detail: str = "", hint: str = "") -> Check:
        check = Check(level, label, detail, hint)
        self.checks.append(check)
        return check

    @property
    def failed(self) -> bool:
        return any(c.level is Level.FAIL for c in self.checks)

    def echo(self) -> None:
        for c in self.checks:
            tag = typer.style(f"[{c.level.value:^5}]", fg=_STYLE[c.level], bold=True)
            typer.echo(f"{tag} {c.label}" + (f": {c.detail}" if c.detail else ""))
            if c.hint:
                for line in c.hint.splitlines():
                    typer.echo(f"        {line}")


def section(title: str) -> None:
    typer.echo("")
    typer.secho(f"=== {title} ===", fg="cyan", bold=True)


# --------------------------------------------------------------------------- #
# Rede
# --------------------------------------------------------------------------- #


def local_ips() -> list[str]:
    """IPv4 locais, ignorando loopback e link-local (169.254.x, como o win-doctor)."""
    ips: set[str] = set()

    # O truque do socket UDP: não envia nada, mas faz o SO escolher a interface de
    # saída. É o IP que o outro lado precisa usar — o que mais interessa aqui.
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        ips.add(sock.getsockname()[0])
    except OSError:
        pass
    finally:
        sock.close()

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass

    return sorted(ip for ip in ips if not ip.startswith(("127.", "169.254.")))


def udp_port_is_free(port: int) -> bool:
    """O sender vai fazer bind aqui. Ocupada = ffmpeg órfão da rodada anterior (§4e)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.bind(("0.0.0.0", port))
        except OSError:
            return False
    return True


def _ping(host: str) -> bool:
    flag = ["-n", "1", "-w", "1000"] if ff.IS_WINDOWS else ["-c", "1", "-W", "1000"]
    try:
        proc = subprocess.run(
            ["ping", *flag, host], capture_output=True, text=True, timeout=6, errors="replace"
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def _arp_mac(host: str) -> str:
    """MAC do host na tabela ARP, ou "" se não houver entrada."""
    args = ["arp", "-a", host] if ff.IS_WINDOWS else ["arp", "-n", host]
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=6, errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return ""
    match = re.search(r"\b([0-9a-fA-F]{1,2}(?:[:-][0-9a-fA-F]{1,2}){5})\b", proc.stdout)
    return match.group(1) if match else ""


def reachable(host: str) -> tuple[bool, str]:
    """`ping` NÃO serve como teste de saúde neste projeto.

    O Firewall do Windows dropa ICMP echo de entrada por padrão: o baseline §4
    registrou 100% de perda no sentido Mac->Windows com a máquina perfeitamente
    online. A prova de vida que vale é o ARP resolver o IP para um MAC — resposta
    em camada 2, que o firewall não filtra. O ping vai junto só para popular a
    tabela ARP e para dar a resposta bonita quando ele funciona.
    """
    if _ping(host):
        return True, "responde ao ping"
    mac = _arp_mac(host)
    if mac:
        return True, f"online via ARP ({mac}) — não responde a ICMP"
    return False, "sem resposta a ICMP e sem entrada ARP"


# --------------------------------------------------------------------------- #
# Checagens
# --------------------------------------------------------------------------- #


def _ask(report: Report, label: str, query):
    """Consulta o ffmpeg; devolve None (e registra FALHA) se ele não responder.

    Cada uma destas propriedades abre um subprocesso novo. Um `ffmpeg -encoders`
    que trava é justamente o sintoma que o doctor existe para diagnosticar
    (driver x versão, baseline §2) — ele não pode ser a coisa que derruba o doctor.
    Quem chama precisa parar em None: seguir com uma resposta vazia produziria um
    segundo diagnóstico, e ele seria falso ("build errado" quando o build está bom).
    """
    try:
        return query()
    except ff.FFmpegError as exc:
        report.add(
            Level.FAIL, label, str(exc).splitlines()[0], "O ffmpeg não respondeu à consulta."
        )
        return None


def check_ffmpeg(report: Report, cfg: Config) -> ff.FFmpegInfo | None:
    try:
        info = ff.load(cfg.paths.ffmpeg)
    except ff.FFmpegError as exc:
        message, _, hint = str(exc).partition("\n")
        report.add(Level.FAIL, "ffmpeg", message, hint.strip())
        return None

    report.add(
        Level.OK, "ffmpeg", f"{info.version} ({info.build or 'sem tag de build'})", str(info.path)
    )

    # baseline §2: a 9.0.1 quebra o NVENC com driver < 610.00. Só vale no Windows.
    if ff.IS_WINDOWS and info.version_tuple >= (9,):
        report.add(
            Level.WARN,
            "versão do ffmpeg",
            f"{info.version} exige driver NVIDIA >= 610.00",
            "A Fase 0 fixou a 8.1 por causa disso (baseline §2). Se o NVENC falhar com\n"
            '"Cannot load nvEncodeAPI64.dll" ou "InitializeEncoder failed", é isto.',
        )

    hw = _ask(report, "encoders de hardware", lambda: enc.hardware_encoders(info.encoders))
    if hw is None:
        return info
    if hw:
        report.add(Level.OK, "encoders de hardware", ", ".join(hw))
    else:
        report.add(
            Level.FAIL if ff.IS_WINDOWS else Level.WARN,
            "encoders de hardware",
            "nenhum",
            "Build errado do ffmpeg (use o full do gyan.dev/BtbN) ou driver ausente.",
        )

    if not ff.IS_WINDOWS:
        # No Mac o encoder do lanstream não entra: quem captura é o Windows e quem
        # recodifica para a Twitch é o OBS. O que interessa aqui é só saber se o
        # VideoToolbox existe, porque é dele que a Fase 4 depende.
        vt = [e for e in hw if e.startswith(("h264_video", "hevc_video"))]
        report.add(
            Level.OK if vt else Level.WARN,
            "VideoToolbox (saída da Fase 4)",
            ", ".join(vt) or "ausente",
        )
        return info

    codec = cfg.video.codec
    try:
        chosen = enc.pick(info.encoders, codec, cfg.video.encoder)
    except (ff.FFmpegError, enc.EncoderError) as exc:
        report.add(Level.FAIL, "encoder escolhido", str(exc).splitlines()[0])
    else:
        # `libx265` é HEVC apesar do nome: quem decide é a família, não o prefixo.
        level = Level.OK if enc.codec_of(chosen) == codec else Level.WARN
        detail = chosen if level is Level.OK else f"{chosen} — o codec pedido era {codec}"
        report.add(
            level,
            "encoder escolhido",
            detail,
            ""
            if level is Level.OK
            else "HEVC é requisito, não preferência: é ele que faz 1080p60 caber\n"
            "em 15 Mbps neste caminho (PLANO §3.3).",
        )
        # O preset é da família, não global: "veryfast" num hevc_nvenc o ffmpeg
        # aceita e ignora. Melhor descobrir aqui do que estranhar a qualidade
        # depois de meia hora no ar.
        try:
            args = enc.preset_args(chosen, cfg.video.preset)
        except enc.EncoderError as exc:
            message, _, hint = str(exc).partition("\n")
            report.add(Level.FAIL, "preset", message, hint.strip())
        else:
            report.add(
                Level.OK,
                "preset",
                " ".join(args) or "o encoder não tem preset",
                "" if cfg.video.preset else "(default da família — [video] preset está vazio)",
            )
    return info


def check_capture(report: Report, info: ff.FFmpegInfo) -> None:
    """Só no Windows: o ddagrab é a captura, e sem ele não há projeto."""
    filters = _ask(report, "ddagrab (captura na GPU)", lambda: info.filters)
    if filters is None:
        return
    if "ddagrab" in filters:
        report.add(Level.OK, "ddagrab (captura na GPU)", "presente")
    else:
        report.add(
            Level.FAIL,
            "ddagrab (captura na GPU)",
            "ausente",
            "Build errado. Use o full build (gyan.dev ou BtbN), não o essentials.",
        )


def check_srt(report: Report, info: ff.FFmpegInfo, cfg: Config) -> None:
    protocols = _ask(report, "protocolo SRT no ffmpeg", lambda: info.protocols)
    if protocols is None:
        return
    has_srt = "srt" in protocols

    if ff.IS_WINDOWS:
        if has_srt:
            report.add(Level.OK, "protocolo SRT no ffmpeg", "presente")
        else:
            report.add(
                Level.FAIL,
                "protocolo SRT no ffmpeg",
                "ausente",
                "O sender depende dele. Use o full build (gyan.dev/BtbN), não o essentials.",
            )
        return

    # Mac: a ausência é o esperado (baseline §1) e não é defeito.
    report.add(
        Level.OK,
        "protocolo SRT no ffmpeg",
        "presente" if has_srt else "ausente — esperado no Homebrew (baseline §1)",
        ""
        if has_srt
        else "Quem recebe é o OBS (traz o próprio libsrt.dylib) e, no preview,\n"
        "o srt-live-transmit. O ffmpeg do Mac não precisa de SRT.",
    )

    slt = ff.find_binary("srt-live-transmit", cfg.paths.srt_live_transmit)
    if slt:
        report.add(Level.OK, "srt-live-transmit", str(slt))
    else:
        report.add(
            Level.FAIL,
            "srt-live-transmit",
            "não encontrado",
            "brew install srt   (é o que faz o `lanstream receive --preview` funcionar)",
        )

    ffplay = ff.find_binary("ffplay", cfg.paths.ffplay)
    if ffplay:
        report.add(Level.OK, "ffplay", str(ffplay))
    else:
        report.add(Level.WARN, "ffplay", "não encontrado", "brew install ffmpeg")


def check_firewall(report: Report, cfg: Config) -> None:
    """Windows: a regra de entrada UDP. Sem ela o SRT nem chega no ffmpeg."""
    if not shutil.which("powershell"):
        report.add(Level.WARN, "firewall", "powershell não encontrado — não deu para checar")
        return
    script = (
        'if (Get-NetFirewallRule -DisplayName "lanstream SRT" -ErrorAction SilentlyContinue) '
        '{ "SIM" } else { "NAO" }'
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=20,
            errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired):
        report.add(Level.WARN, "firewall", "não deu para checar")
        return

    if proc.stdout.strip() == "SIM":
        report.add(Level.OK, "firewall", 'regra "lanstream SRT" existe')
    else:
        report.add(
            Level.FAIL,
            "firewall",
            'regra "lanstream SRT" ausente',
            "Num PowerShell COMO ADMINISTRADOR, uma vez só:\n"
            f'  New-NetFirewallRule -DisplayName "lanstream SRT" -Direction Inbound '
            f"-Protocol UDP -LocalPort {cfg.network.port} -Action Allow -Profile Private",
        )


def _check_host_identity(report: Report, host: str, ips: list[str]) -> bool:
    """O `host` é sempre o IP do sender. Cada lado erra de um jeito diferente.

    No Windows ele deve ser um IP desta máquina — se não for, o IP mudou e a URL
    que o Mac usa aponta para o vazio, coisa que só apareceria no meio da live.
    No Mac é o oposto: apontar para si mesmo é o engano, e é exatamente o que a
    ambiguidade do campo induzia (`docs/fase1.md` §1).
    """
    if ff.IS_WINDOWS:
        if host in ips:
            report.add(Level.OK, "host do sender", f"{host} — é esta máquina, como deve ser")
            return True
        else:
            report.add(
                Level.FAIL,
                "host do sender",
                f"{host} não é um IP desta máquina ({', '.join(ips) or 'nenhum'})",
                "O IP mudou. Atualize [network] host aqui e no Mac — senão o OBS vai\n"
                "conectar num endereço que não existe mais.",
            )
            return False
    elif host in ips:
        report.add(
            Level.FAIL,
            "host do sender",
            f"{host} é esta máquina",
            "[network] host é sempre o IP do WINDOWS, também aqui — é para lá que\n"
            "o OBS conecta. Para o alvo do teste de alcance existe o [network] peer.",
        )
        return False
    return True


def check_network(report: Report, cfg: Config) -> None:
    ips = local_ips()
    if ips:
        report.add(Level.OK, "IPs locais", ", ".join(ips))
    else:
        report.add(Level.WARN, "IPs locais", "nenhum IPv4 utilizável")

    port = cfg.network.port
    if ff.IS_WINDOWS:
        # O sender é quem faz bind. Porta ocupada quase sempre é ffmpeg órfão.
        if udp_port_is_free(port):
            report.add(Level.OK, f"porta {port}/UDP", "livre para o sender")
        else:
            # AVISO, não FALHA: o caso mais comum é o sender já estar no ar, e o
            # doctor precisa ser seguro de rodar durante uma sessão. Só depois de
            # confirmar que não há sender é que a porta ocupada vira problema.
            report.add(
                Level.WARN,
                f"porta {port}/UDP",
                "ocupada",
                "Esperado se o `lanstream send` já estiver rodando — neste caso, ignore.\n"
                "Se não estiver, é ffmpeg órfão de uma rodada anterior segurando a porta:\n"
                "  Get-Process ffmpeg | Stop-Process",
            )

    host = cfg.network.host
    if not host:
        report.add(
            Level.WARN,
            "host do sender",
            "não configurado",
            "Preencha [network] host no lanstream.toml com o IP do Windows —\n"
            "é o endereço em que o OBS conecta, e vale nas duas máquinas.",
        )
    elif not _check_host_identity(report, host, ips) and not ff.IS_WINDOWS:
        # Host errado no Mac: medir alcance contra ele seria um ping em si mesmo,
        # que passa de graça e contradiz visualmente a falha logo acima.
        return

    # O alcance mede a OUTRA ponta. No Mac ela é o sender; no Windows, o `peer`.
    # Sem peer o teste simplesmente não existe do lado do Windows — e não faz
    # falta, porque quem inicia a conexão é o Mac. Medir daqui é conveniência.
    target = cfg.network.peer if ff.IS_WINDOWS else host
    if not target:
        return

    up, detail = reachable(target)
    report.add(
        Level.OK if up else Level.FAIL,
        f"alcance até {target}",
        detail,
        "O Firewall do Windows dropa ICMP por padrão (baseline §4); ARP é a prova de vida.\n"
        "O que decide mesmo é o handshake SRT."
        if up and "ARP" in detail
        else ""
        if up
        else "Máquina desligada, IP mudou, ou as duas estão em redes diferentes.\n"
        "O ARP também não resolveu, então não é só o firewall.",
    )


def run(cfg: Config) -> int:
    """Imprime o diagnóstico completo. Devolve o código de saída."""
    section("SISTEMA")
    role = (
        "sender (Windows)" if ff.IS_WINDOWS else "receiver (Mac)" if ff.IS_MACOS else "indefinido"
    )
    typer.echo(f"  {platform.platform()}")
    typer.echo(f"  Python {platform.python_version()} — papel: {role}")
    typer.echo(f"  config: {cfg.source or 'nenhum arquivo (usando os defaults embutidos)'}")

    section("VÍDEO")
    v = cfg.video
    typer.echo(
        f"  {v.width}x{v.height}@{v.fps}  {v.codec} {v.bitrate} CBR"
        f"  gop={v.gop}  monitor={v.monitor}"
    )
    typer.echo(f"  SRT buffer: {cfg.network.latency_ms} ms")

    section("CHECAGENS")
    report = Report()
    info = check_ffmpeg(report, cfg)
    if info is not None:
        if ff.IS_WINDOWS:
            check_capture(report, info)
        check_srt(report, info, cfg)
    if ff.IS_WINDOWS:
        check_firewall(report, cfg)
    check_network(report, cfg)
    report.echo()

    section("URLs")
    typer.echo("  sender (Windows):  " + cfg.network.url_for_ffmpeg(mode="listener"))
    if cfg.network.host:
        typer.echo("  OBS / ffmpeg:      " + cfg.network.url_for_ffmpeg(mode="caller"))
        typer.echo("  srt-live-transmit: " + cfg.network.url_for_srt_live_transmit())
        typer.echo("  (o latency muda de unidade entre os dois — µs no OBS, ms no slt)")
    else:
        typer.echo("  as URLs do lado do Mac precisam de [network] host preenchido")
    if ff.IS_WINDOWS and not cfg.network.peer:
        typer.echo("  (opcional: [network] peer = IP do Mac faz o doctor medir o alcance daqui)")

    typer.echo("")
    if report.failed:
        typer.secho("Há FALHAs acima. Resolva antes de tentar transmitir.", fg="red", bold=True)
        return 1
    if any(c.level is Level.WARN for c in report.checks):
        typer.secho("Sem falhas. Há avisos — leia antes de ir ao ar.", fg="yellow", bold=True)
        return 0
    typer.secho("Tudo certo deste lado.", fg="green", bold=True)
    return 0


def main(cfg: Config) -> None:
    sys.exit(run(cfg))
