"""Monta e supervisiona o ffmpeg do lado do Windows.

O argv sai daqui como lista de strings, é impresso antes de rodar e pode ser
colado num PowerShell sem mudar nada. Isso não é capricho: toda a Fase 0 foi
feita colando comando na mão, e quando algo quebrar às 22h de um sábado o
caminho de volta é comparar o que o `lanstream` montou com o que o
`win-test-video.ps1` montava.

A ordem das flags segue a do script da Fase 0 de propósito — entrada, filtro,
encoder, taxa, mux, URL — para que um `diff` entre os dois seja legível.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import encoders as enc
from . import ffmpeg as ff
from .config import Config, parse_bitrate

# Quanto esperar o ffmpeg sair sozinho depois do Ctrl+C. Ele escreve o trailer do
# MPEG-TS e fecha o socket SRT nesse intervalo; matar antes é o que deixa a porta
# 9000 presa e faz o próximo `send` falhar com "Address already in use".
GRACE_SECONDS = 5.0

# Linha de progresso do ffmpeg ("frame=  123 fps= 58 ..."). Ela vem terminada em
# \r, não \n — por isso a leitura abaixo não usa readline().
_PROGRESS_RE = re.compile(r"^(frame|size)=")


class SenderError(Exception):
    """Falha ao montar ou rodar o sender — mensagem pronta para o usuário final."""


@dataclass
class Plan:
    """O comando decidido, antes de virar processo."""

    argv: list[str]
    encoder: str
    url: str
    binary: Path | None

    @property
    def shell_line(self) -> str:
        """A mesma coisa, colável num terminal."""
        return " ".join(_quote(a) for a in self.argv)


def _quote(arg: str) -> str:
    # A URL SRT tem `&`, que tanto o cmd quanto o PowerShell interpretam.
    return f'"{arg}"' if re.search(r"[\s&?|<>^]", arg) else arg


def capture_filter(cfg: Config, *, hwdownload: bool) -> str:
    """A cadeia de filtros do ddagrab.

    Nada entre o `ddagrab` e o NVENC: o baseline testou as alternativas e as duas
    que "deveriam" funcionar falham neste build — `hwmap=derive_device=cuda`
    devolve ENOSYS e o `scale_d3d11` não configura o pad de saída. Passar direto
    dá o mesmo desempenho (58 fps, 0.98x) sem filtro nenhum. Só o encoder de
    software precisa dos frames na RAM, e aí o download é obrigatório.
    """
    chain = f"ddagrab={cfg.video.monitor}:framerate={cfg.video.fps}"
    if hwdownload:
        chain += ",hwdownload,format=bgra,format=nv12"
    return chain


def build(cfg: Config, info: ff.FFmpegInfo | None = None, *, encoder: str = "") -> Plan:
    """Decide o encoder e monta o argv. Não executa nada.

    `info` None significa "não consultei nenhum ffmpeg" — é o caso do `--dry-run`
    rodado no Mac para ver o comando que o Windows vai usar. Aí a escolha se apoia
    só na config, e quem chama avisa que não houve verificação.
    """
    available = info.encoders if info is not None else set()
    try:
        chosen = enc.pick(available, cfg.video.codec, encoder or cfg.video.encoder)
        preset = enc.preset_args(chosen, cfg.video.preset)
    except enc.EncoderError as exc:
        raise SenderError(str(exc)) from None

    profile = enc.profile_of(chosen)
    bitrate = str(cfg.video.bitrate)
    url = cfg.network.url_for_ffmpeg(mode="listener")
    binary = info.path if info is not None else None

    argv = [
        str(binary) if binary else "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "info",
        "-stats",
        # Sem isto o ffmpeg disputa o teclado do console com quem o supervisiona.
        "-nostdin",
        # O ddagrab precisa de um device D3D11 já criado; ele não cria o seu.
        "-init_hw_device",
        "d3d11va",
        "-filter_complex",
        capture_filter(cfg, hwdownload=profile.needs_hwdownload),
        "-c:v",
        chosen,
        *preset,
        *profile.extra,
        # CBR de verdade: os três iguais. bufsize = 1 s de vídeo é o que a Fase 0
        # usou; um bufsize maior deixaria a taxa oscilar acima do que a rede
        # aguenta, e o teto aqui é de transporte, não de qualidade (PLANO §3.3).
        "-b:v",
        bitrate,
        "-maxrate",
        bitrate,
        "-bufsize",
        bitrate,
        "-g",
        str(cfg.video.gop),
        # B-frames desligados como na Fase 0. O §3.1 diz que dá para ligar
        # (latência é barata aqui), mas isso é knob da Fase 7, com medição junto.
        "-bf",
        "0",
        "-f",
        "mpegts",
        url,
    ]
    return Plan(argv=argv, encoder=chosen, url=url, binary=binary)


def plan_for(cfg: Config, encoder: str = "", consult_ffmpeg: bool = True) -> Plan:
    """`build` + a busca do binário local.

    `consult_ffmpeg=False` é o dry-run fora do Windows: o ffmpeg desta máquina não
    é o que vai rodar, e consultá-lo daria uma resposta pior que nenhuma — no Mac
    a cadeia escolheria `hevc_videotoolbox` e imprimiria um comando que ninguém
    vai usar. Sem consulta, vale a preferência da config, que é o que o Windows
    também vai escolher.
    """
    info = ff.load(cfg.paths.ffmpeg) if consult_ffmpeg else None
    return build(cfg, info, encoder=encoder)


# --------------------------------------------------------------------------- #
# Execução
# --------------------------------------------------------------------------- #


def stream_output(pipe, echo) -> None:
    """Repassa o stderr do ffmpeg, tratando \\r como fim de linha.

    O `readline()` normal travaria até o próximo \\n, e a linha de progresso do
    ffmpeg nunca manda um: ela se reescreve com \\r. Sem isto o console fica mudo
    por minutos e parece que o sender morreu.
    """
    buffer = b""
    fd = pipe.fileno()
    while True:
        try:
            chunk = os.read(fd, 4096)
        except (OSError, ValueError):
            break
        if not chunk:
            break
        buffer += chunk
        *done, buffer = re.split(rb"[\r\n]", buffer)
        for raw in done:
            line = raw.decode("utf-8", errors="replace").rstrip()
            if line:
                echo(line, bool(_PROGRESS_RE.match(line)))
    if buffer.strip():
        echo(buffer.decode("utf-8", errors="replace").rstrip(), False)


def run(plan: Plan, echo) -> int:
    """Roda o ffmpeg até o Ctrl+C ou até ele morrer. Devolve o código de saída.

    O processo **não** é posto num grupo próprio: no Windows é justamente a
    herança do grupo do console que faz o Ctrl+C chegar ao ffmpeg, que então
    fecha o mux e o socket sozinho. Criar um grupo novo (`CREATE_NEW_PROCESS_GROUP`)
    pareceria mais limpo e seria pior — o ffmpeg não receberia nada e só sairia
    no `kill`, deixando o TS truncado e a porta ocupada por alguns segundos.
    """
    try:
        proc = subprocess.Popen(
            plan.argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise SenderError(f"não consegui executar {plan.argv[0]}: {exc}") from None

    interrupted = False
    try:
        stream_output(proc.stderr, echo)
        return proc.wait()
    except KeyboardInterrupt:
        interrupted = True
        return _shutdown(proc, echo)
    finally:
        if not interrupted and proc.poll() is None:
            # Chegamos aqui sem Ctrl+C e com o ffmpeg vivo: só acontece se a
            # leitura do stderr morrer antes dele. Órfão segurando a 9000 é
            # justamente o que a Fase 2 promete não deixar acontecer.
            _shutdown(proc, echo)
        if proc.stderr:
            proc.stderr.close()


def _shutdown(proc: subprocess.Popen, echo) -> int:
    """Espera o ffmpeg sair sozinho; insiste com terminate/kill se ele não sair.

    O stderr continua sendo drenado numa thread daemon. Não é zelo com o log: um
    pipe cheio bloqueia quem escreve, e o ffmpeg ainda tem o que dizer depois do
    sinal ("Exiting normally, received signal 2", o resumo do mux). Parar de ler
    aqui poderia travá-lo exatamente no ponto em que queremos que ele termine.
    """
    if proc.stderr is not None:
        threading.Thread(target=stream_output, args=(proc.stderr, echo), daemon=True).start()
    echo("encerrando o ffmpeg (fechando o mux e a porta SRT)...", False)
    deadline = time.monotonic() + GRACE_SECONDS
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return proc.returncode
        time.sleep(0.1)

    echo(f"o ffmpeg não saiu em {GRACE_SECONDS:.0f}s — mandando terminate", False)
    proc.terminate()
    try:
        return proc.wait(timeout=GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        echo("ainda vivo — kill", False)
        proc.kill()
        return proc.wait()


def check_platform(dry_run: bool) -> str:
    """O sender é Windows. Fora dele só o --dry-run faz sentido.

    Vale a pena permitir o dry-run em qualquer SO: montar o comando do Windows
    sentado no Mac é como se confere a URL e o encoder sem trocar de máquina.
    """
    if ff.IS_WINDOWS:
        return ""
    if dry_run:
        return (
            f"este é {sys.platform}, não o Windows: o comando abaixo é o que rodaria lá.\n"
            "O ffmpeg desta máquina não foi consultado — o encoder vem da config."
        )
    raise SenderError(
        "`lanstream send` só roda no Windows — a captura é o ddagrab (Desktop Duplication).\n"
        "  No Mac o lado de cá é o OBS (Fase 4) ou `lanstream receive --preview`.\n"
        "  Para só ver o comando: lanstream send --dry-run"
    )


def summary(cfg: Config, plan: Plan) -> list[str]:
    """As três linhas que respondem 'o que vai no ar' antes de ir ao ar."""
    v = cfg.video
    mbps = parse_bitrate(v.bitrate, "[video] bitrate") / 1_000_000
    return [
        f"{plan.encoder}  {mbps:g} Mbps CBR  {v.fps} fps  gop={v.gop}",
        # width/height não entram no comando: o ddagrab entrega a resolução que o
        # monitor tiver, e não há escala no caminho (ver docs/fase2.md §2). São
        # expectativa declarada — se a saída do ffmpeg discordar, é o monitor que
        # mudou, e é bom que a linha acima esteja na tela para comparar.
        f"monitor {v.monitor} — esperado {v.width}x{v.height}, "
        f"buffer SRT {cfg.network.latency_ms} ms",
        f"escutando em {plan.url}",
    ]
