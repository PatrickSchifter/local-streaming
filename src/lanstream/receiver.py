"""O lado do Mac: `lanstream receive` — o preview de diagnóstico.

Existe para responder **"o problema é a rede ou é o OBS?"** em cinco segundos. Se
a imagem aparece aqui e não aparece no OBS, o caminho está bom e a questão é
configuração da fonte; se não aparece nem aqui, o problema é antes.

Por que dois processos em vez de um: o **ffmpeg do Homebrew não tem libsrt**
(`docs/baseline.md` §1). Quem fala SRT no Mac é o `srt-live-transmit`, que
entrega MPEG-TS puro no stdout; o `ffplay` só consome. Isso não é contorno feio —
é a mesma divisão que o OBS faz internamente, e tem a vantagem de o
`srt-live-transmit` ser o único que enxerga os contadores do libsrt.

Duas coisas custaram tempo e estão codificadas aqui:

* **As estatísticas vão para ARQUIVO, nunca para a tela.** O `-s` do
  `srt-live-transmit` escreve em stdout, e stdout é por onde o vídeo passa —
  ligar as estatísticas sem `-statsout` injeta JSON no meio do MPEG-TS e o
  ffplay morre com erro de decodificação, o que parece problema de rede.
* **Conectar aqui consome a conexão do sender.** O ffmpeg em modo SRT `listener`
  atende **um** cliente e trata a desconexão como fatal. Rodar o preview enquanto
  o OBS está pegando o stream tira o OBS do ar; e uma sonda que não conecta não
  distingue "sender morto" de "sender ocupado" — foi assim que eu diagnostiquei
  errado em 31/08 (`docs/windows.md` §4).
"""

from __future__ import annotations

import signal
import subprocess
import threading
from dataclasses import dataclass

from . import ffmpeg as ff
from .config import Config

# ⛔ Os contadores do libsrt NÃO são coletáveis por aqui, e isso foi medido em
# 31/08 com a 1.5.6 do Homebrew. A dívida da Fase 2 (`RCV-DROPPED`, ver
# `docs/proximos-testes.md` §F2.3) continua aberta, agora com motivo:
#
#   * com `-s` e a saída em `file://con`, a própria ferramenta recusa:
#     "file://con with -v or -r or -s would result in mixing the data and text
#     info" — o vídeo e o texto disputariam o mesmo stdout;
#   * `-statsout <arquivo>` é aceito junto com `-s`, e **não escreve nada** nos
#     três formatos (`json`, `csv`, `default`), testados com 9 s de stream a
#     8 Mbps, que dariam ~12 relatórios;
#   * `file:///dev/null` como saída é recusado com "Unsupported target type" —
#     o `file://` desta ferramenta existe só como `file://con`.
#
# Ou seja: ou se consome o stream, ou se leem os contadores. Uma flag `--stats`
# aqui só poderia produzir silêncio, e silêncio com cara de medição é pior que
# não ter a medição.


class ReceiverError(Exception):
    """Falha ao montar ou rodar o preview — mensagem pronta para o usuário final."""


@dataclass
class Preview:
    """Os dois comandos decididos, antes de virarem processo."""

    transmit: list[str]
    player: list[str]
    url: str

    @property
    def shell_line(self) -> str:
        return (
            " ".join(_quote(a) for a in self.transmit)
            + " \\\n  | "
            + " ".join(_quote(a) for a in self.player)
        )


def _quote(arg: str) -> str:
    # A URL SRT tem `&` e `?`, que o shell interpreta.
    return f'"{arg}"' if any(c in arg for c in " &?|<>") else arg


def build(cfg: Config, *, host: str = "") -> Preview:
    """Monta os dois argvs. Não executa nada — o `--dry-run` para aqui."""
    slt = ff.find_binary("srt-live-transmit", cfg.paths.srt_live_transmit)
    if slt is None:
        raise ReceiverError(
            "srt-live-transmit não encontrado — é ele que fala SRT neste lado.\n  brew install srt"
        )
    player = ff.find_binary("ffplay", cfg.paths.ffplay)
    if player is None:
        raise ReceiverError("ffplay não encontrado.\n  brew install ffmpeg")

    # Atenção à unidade: aqui a latência é em MILIssegundos. O ffmpeg e o OBS
    # querem MICROssegundos na mesma opção (baseline §5).
    url = cfg.network.url_for_srt_live_transmit(host or None)

    # `-a no` desliga o auto-reconnect. Num transporte de produção ele seria
    # desejável; aqui é o oposto do que se quer: com ele ligado, o sender morrer
    # não fecha o pipe, o ffplay nunca vê EOF e a janela fica parada no último
    # quadro — a ferramenta que existe para dizer "o sender caiu" ficaria muda
    # exatamente na hora em que ele cai.
    transmit = [str(slt), url, "file://con", "-a", "no"]

    return Preview(
        transmit=transmit,
        player=[
            str(player),
            "-hide_banner",
            "-loglevel",
            "info",
            # Mostra o quadro assim que chega, em vez de encher buffer: é o que
            # torna o preview útil para medir latência a olho. Em produção quem
            # bufferiza é o OBS, e ali o ajuste é outro.
            "-fflags",
            "nobuffer",
            "-flags",
            "low_delay",
            "-framedrop",
            # Sai quando a entrada acaba, em vez de congelar no último quadro.
            # Preview que continua aberto depois do fim do stream mente sobre o
            # estado do sender.
            "-autoexit",
            "-window_title",
            f"lanstream preview — {cfg.network.host or 'sender'}",
            "-",
        ],
        url=url,
    )


def run(plan: Preview, echo) -> int:
    """Roda os dois processos ligados por um pipe, até o Ctrl+C ou o fim do stream.

    O `srt-live-transmit` não vai para um grupo próprio, pela mesma razão do
    sender: é a herança do grupo do terminal que faz o Ctrl+C chegar nele. O
    ffplay também sai sozinho quando o pipe fecha.
    """
    try:
        transmit = subprocess.Popen(plan.transmit, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as exc:
        raise ReceiverError(f"não consegui executar {plan.transmit[0]}: {exc}") from None

    try:
        player = subprocess.Popen(
            plan.player, stdin=transmit.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
    except OSError as exc:
        transmit.kill()
        raise ReceiverError(f"não consegui executar {plan.player[0]}: {exc}") from None

    # Fechar a nossa cópia do pipe é o que faz o srt-live-transmit receber EPIPE
    # quando o ffplay morre; sem isso ele ficaria escrevendo para ninguém.
    if transmit.stdout is not None:
        transmit.stdout.close()

    # O stderr é drenado por uma thread, e não lido no fim: ele é bufferizado por
    # ser pipe, e um processo morto a sinal perde o que estiver no buffer. Ler só
    # no fim fazia o "SRT source connected" sumir justamente nas execuções que
    # conectaram, e o aviso de "não houve conexão" saía numa sessão saudável.
    dito: list[str] = []

    def drena():
        if transmit.stderr is None:
            return
        for linha in transmit.stderr:
            texto = linha.decode("utf-8", "replace").rstrip()
            if texto:
                dito.append(texto)

    tubo = threading.Thread(target=drena, daemon=True)
    tubo.start()

    try:
        code = player.wait()
    except KeyboardInterrupt:
        code = 0
    finally:
        for proc in (player, transmit):
            if proc.poll() is None:
                proc.send_signal(signal.SIGINT)
        for proc in (player, transmit):
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    tubo.join(timeout=2)
    if not any("connected" in linha.lower() for linha in dito):
        # Parar em "Media path" sem conectar é o sintoma nº 1 do protocolo, e a
        # mensagem existe para que ninguém o leia como "a rede está ruim".
        echo(
            "não houve conexão SRT. As duas causas, na ordem:\n"
            "  1. o sender não está no ar (o log dele diz por quê);\n"
            "  2. o sender ESTÁ no ar e já serve outro cliente — o OBS, por\n"
            "     exemplo. O listener atende um só, e de fora as duas causas\n"
            "     têm a mesma aparência."
        )
    return code
