"""Log em arquivo, rotativo — o que responde "o que aconteceu às 22h14?".

O console serve para quem está olhando; este módulo serve para quem não estava.
Numa sessão de jogo de três horas ninguém acompanha o terminal, e quando algo
some do ar a pergunta é sempre sobre o passado.

Duas decisões que valem explicação:

* **A linha de progresso entra por amostragem, não inteira.** Ela se reescreve
  várias vezes por segundo; guardá-la toda encheria o arquivo de ruído e faria a
  rotação descartar justamente as linhas de erro, que são raras. Uma amostra a
  cada 30 s vira um batimento — fps, bitrate e `speed` ao longo do tempo — que é
  exatamente o que se quer reler depois. As linhas que **não** são progresso
  entram todas: são poucas e são as que explicam.
* **Rotação por tamanho, não por data.** O que importa é caber, e uma sessão
  longa gera muito mais linha que um dia inteiro parado.
"""

from __future__ import annotations

import logging
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

FORMATO = "%(asctime)s %(levelname)-5s %(message)s"
DATA = "%Y-%m-%d %H:%M:%S"


def caminho_padrao(configurado: str = "") -> Path:
    """`logs/` ao lado de onde se roda, salvo se a config disser outra coisa.

    O diretório `logs/` já é ignorado pelo git desde a Fase 1 — o arquivo tem
    caminho de máquina, IP e nome de device, e nada disso volta para o repositório.
    """
    return (Path(configurado) if configurado else Path.cwd() / "logs") / "lanstream.log"


def configurar(destino: Path, *, max_mb: int = 5, manter: int = 5, verbose: bool = False):
    """Prepara o logger. Devolve None se não der para escrever — nunca levanta.

    `verbose` liga o nível DEBUG, e é isso que faz a linha de progresso ser
    guardada **inteira** em vez de amostrada: quem chama registra o progresso em
    DEBUG e a amostra em INFO (ver `cli.py`). Não há handler de console aqui de
    propósito — o console já recebe tudo do ffmpeg direto; duplicar as mesmas
    linhas por um segundo caminho só faria ruído.

    Não poder gravar log é motivo para avisar, não para impedir a transmissão:
    quem está prestes a jogar não quer descobrir que o `send` não sobe porque uma
    pasta não pôde ser criada.
    """
    logger = logging.getLogger("lanstream")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            destino, maxBytes=max_mb * 1024 * 1024, backupCount=manter, encoding="utf-8"
        )
    except OSError:
        return None
    handler.setFormatter(logging.Formatter(FORMATO, DATA))
    logger.addHandler(handler)
    return logger


class Batimento:
    """Deixa passar uma linha de progresso a cada `intervalo` segundos."""

    def __init__(self, intervalo: float = 30.0) -> None:
        self.intervalo = intervalo
        self._ultimo = 0.0

    def passa(self) -> bool:
        agora = time.monotonic()
        if agora - self._ultimo < self.intervalo:
            return False
        self._ultimo = agora
        return True
