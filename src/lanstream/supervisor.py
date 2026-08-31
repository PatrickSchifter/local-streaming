"""Mantém o sender no ar sem ação humana — o `--watch` da Fase 5.

O problema que ele resolve não é hipotético: o ffmpeg em modo SRT `listener`
**morre toda vez que o receptor desconecta**, porque trata a queda do caller como
erro fatal (`proximos-testes.md`, regra 1). Numa sessão real isso acontece sempre
que alguém troca de cena no OBS, que o Wi-Fi engasga, ou que a captura perde o
desktop. Sem supervisor, cada um desses eventos exige alguém ir até o Windows.

E metade do par já se recupera de graça: o Media Source do OBS tenta reconectar a
cada 2 s por conta própria — medido na Fase 2, ele agarrou o sender ~22 s antes de
alguém pedir. Faltava só o lado do Windows voltar a escutar; é o que este módulo
faz.

Três decisões que vieram de medição, não de gosto:

* **Backoff que se reseta.** Uma sessão que rodou meia hora e caiu não merece a
  mesma espera de uma que morre em dois segundos. Sem o reset, uma noite de jogo
  com três quedas espaçadas terminaria esperando um minuto para reerguer.
* **Conferir a porta antes de subir.** Se a 9000 continua ocupada, o próximo
  ffmpeg morre com `Address already in use` e o supervisor entraria num laço
  reiniciando algo que não pode subir. Esperar a porta é mais honesto que insistir.
* **Nem todo motivo merece reinício.** Device de áudio que sumiu e porta ocupada
  se repetiriam iguais para sempre; reiniciar aí é ruído, não robustez.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import doctor as doc
from . import sender as snd
from .config import Config

# A espera cresce até este teto. Um minuto é o bastante para uma queda de rede
# passar e curto o bastante para ninguém achar que travou.
BACKOFF_INICIAL = 1.0
BACKOFF_TETO = 60.0

# Execução que durou mais que isto zera o backoff: foi uma sessão de verdade, não
# uma falha de partida.
DURACAO_SAUDAVEL = 60.0

# Quantas vezes seguidas se tenta antes de desistir, sem contar as que zeraram o
# backoff. Existe para que um erro permanente termine com mensagem em vez de
# rodar a noite toda em silêncio.
TENTATIVAS = 20

# Quanto se espera a porta 9000 vagar antes de tentar subir mesmo assim.
ESPERA_PORTA = 15.0


@dataclass
class Sessao:
    """O que aconteceu ao longo de uma supervisão inteira."""

    execucoes: int = 0
    reinicios: int = 0
    motivos: list[str] = field(default_factory=list)
    segundos_no_ar: float = 0.0

    def resumo(self) -> list[str]:
        linhas = [
            f"{self.execucoes} execuç{'ão' if self.execucoes == 1 else 'ões'}, "
            f"{self.reinicios} reinício(s), {self.segundos_no_ar / 60:.1f} min no ar"
        ]
        for motivo in dict.fromkeys(self.motivos):
            linhas.append(f"  - {motivo} ({self.motivos.count(motivo)}x)")
        return linhas


def esperar_porta(cfg: Config, echo, limite: float = ESPERA_PORTA) -> bool:
    """Espera a porta do sender vagar. Devolve False se ela não vagou.

    O ffmpeg leva um instante para fechar o socket depois de morrer, e subir o
    próximo em cima disso dá `Address already in use` — que o supervisor
    classificaria como "não reiniciar" e a sessão morreria por um problema que
    some sozinho em um segundo.
    """
    fim = time.monotonic() + limite
    avisou = False
    while time.monotonic() < fim:
        if doc.udp_port_is_free(cfg.network.port):
            return True
        if not avisou:
            echo(f"esperando a porta {cfg.network.port}/UDP vagar...")
            avisou = True
        time.sleep(0.5)
    return doc.udp_port_is_free(cfg.network.port)


def supervisionar(cfg: Config, plan: snd.Plan, echo, anunciar) -> Sessao:
    """Roda o sender em laço até o Ctrl+C ou até um motivo que não se reergue.

    `echo` recebe as linhas do ffmpeg (assinatura do `sender.run`); `anunciar`
    recebe as mensagens do próprio supervisor, que merecem destaque diferente.
    """
    sessao = Sessao()
    espera = BACKOFF_INICIAL

    # Contador explícito, e não `for ... in range()`: o teto conta falhas
    # SEGUIDAS, e uma execução saudável precisa zerá-lo. Num `for`, zerar a
    # variável não tem efeito nenhum — a iteração seguinte a reatribui — e o
    # supervisor desistiria no meio de uma noite tranquila por causa de vinte
    # quedas espaçadas ao longo de horas.
    tentativa = 0
    while tentativa < TENTATIVAS:
        tentativa += 1
        if not esperar_porta(cfg, anunciar):
            anunciar(
                f"a porta {cfg.network.port}/UDP continua ocupada depois de "
                f"{ESPERA_PORTA:.0f}s — provavelmente há um ffmpeg órfão.\n"
                "  Windows:  Get-Process ffmpeg | Stop-Process"
            )
            return sessao

        sessao.execucoes += 1
        resultado = snd.run(plan, echo)
        sessao.segundos_no_ar += resultado.segundos
        if resultado.motivo:
            sessao.motivos.append(resultado.motivo)

        if resultado.interrompido:
            anunciar("encerrado a pedido.")
            return sessao
        if not resultado.reiniciar:
            anunciar(f"não vou reerguer: {resultado.motivo}.")
            return sessao

        if resultado.segundos >= DURACAO_SAUDAVEL:
            # Sessão de verdade antes da queda: a próxima falha recomeça do zero,
            # tanto na espera quanto na contagem.
            espera = BACKOFF_INICIAL
            tentativa = 0
        sessao.reinicios += 1
        anunciar(
            f"o ffmpeg saiu ({resultado.code}) depois de {resultado.segundos:.0f}s: "
            f"{resultado.motivo}.\n  reerguendo em {espera:.0f}s "
            f"(tentativa {tentativa} de {TENTATIVAS})"
        )
        try:
            time.sleep(espera)
        except KeyboardInterrupt:
            anunciar("encerrado a pedido durante a espera.")
            return sessao
        espera = min(espera * 2, BACKOFF_TETO)

    anunciar(f"desisti depois de {TENTATIVAS} tentativas seguidas sem sucesso.")
    return sessao
