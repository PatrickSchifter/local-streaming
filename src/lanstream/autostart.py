"""Sobe o sender sozinho no login do Windows.

O último elo da Fase 5. Com o `--watch` o sender se reergue quando cai, e com o
Media Source do OBS reconectando a cada 2 s o par se recupera sozinho — mas nada
disso ajuda se ninguém abriu o terminal depois de um reboot. Esta é a peça que
tira a última ação humana do caminho.

**Um `.cmd` na pasta Inicializar, e não uma tarefa agendada.** O Task Scheduler
faria isso "mais direito", e seria pior aqui: tarefa agendada roda sem console, e
sem console **o Ctrl+C não tem onde chegar** — que é exatamente o mecanismo que a
Fase 2 mediu para o ffmpeg encerrar limpo, escrevendo o trailer e soltando a
porta (`docs/fase2.md` §5). Um atalho na inicialização abre uma janela de console
de verdade: dá para ver o que está acontecendo e dá para encerrar do jeito que já
foi testado. Desinstalar é apagar um arquivo.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import ffmpeg as ff

NOME = "lanstream.cmd"


class AutostartError(Exception):
    """Falha ao instalar ou remover o auto-start — mensagem pronta para o usuário."""


def pasta_startup() -> Path:
    """A pasta Inicializar do usuário atual (não a de todos os usuários).

    A do usuário não precisa de administrador, e este projeto roda numa máquina
    de uma pessoa só.
    """
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise AutostartError("não achei %APPDATA% — isto só funciona no Windows.")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def conteudo(projeto: Path, python: Path, extras: str = "") -> str:
    """O `.cmd` que será escrito. Função pura, para poder ser conferida sem instalar.

    Chama `python -m lanstream.cli` em vez do `lanstream.exe`: o console script
    depende de como o pacote foi instalado, e o módulo funciona em qualquer caso —
    inclusive num `uv pip install -e` que não tenha posto o `Scripts` no PATH.

    O `pause` no fim não é enfeite: se o comando falhar na partida, sem ele a
    janela fecha antes de alguém ler o motivo, e o sintoma vira "não subiu".
    """
    return (
        "@echo off\r\n"
        "rem Gerado por `lanstream install-autostart`.\r\n"
        "rem Para desativar: apague este arquivo, ou rode\r\n"
        "rem   lanstream install-autostart --remove\r\n"
        f'cd /d "{projeto}"\r\n'
        f'"{python}" -m lanstream.cli send --watch{extras}\r\n'
        "echo.\r\n"
        "echo O sender encerrou. Feche esta janela ou leia o motivo acima.\r\n"
        "pause\r\n"
    )


def alvo() -> Path:
    return pasta_startup() / NOME


def instalar(extras: str = "", *, escrever: bool = True) -> tuple[Path, str]:
    """Devolve (caminho, conteúdo). Com `escrever=False` não toca no disco."""
    if not ff.IS_WINDOWS and escrever:
        raise AutostartError(
            "o auto-start é do lado do Windows — é lá que o sender roda.\n"
            "  Para ver o que seria escrito: lanstream install-autostart --dry-run"
        )
    projeto = Path.cwd()
    texto = conteudo(projeto, Path(sys.executable), extras)
    caminho = alvo() if ff.IS_WINDOWS else Path("%APPDATA%") / "…" / "Startup" / NOME
    if escrever:
        try:
            caminho.parent.mkdir(parents=True, exist_ok=True)
            caminho.write_text(texto, encoding="utf-8", newline="")
        except OSError as exc:
            raise AutostartError(f"não consegui escrever {caminho}: {exc}") from None
    return caminho, texto


def remover() -> Path | None:
    """Apaga o atalho. Devolve o caminho apagado, ou None se não havia nada."""
    if not ff.IS_WINDOWS:
        raise AutostartError("o auto-start é do lado do Windows.")
    caminho = alvo()
    if not caminho.exists():
        return None
    try:
        caminho.unlink()
    except OSError as exc:
        raise AutostartError(f"não consegui apagar {caminho}: {exc}") from None
    return caminho
