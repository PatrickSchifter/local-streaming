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
from .config import find_config_file

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


def _sem_porcento(*caminhos: Path) -> None:
    """Recusa caminhos com `%`. O batch expande variável mesmo dentro de aspas.

    `C:\\Users\\100%teste` viraria outra coisa na hora do login, e o erro
    apareceria depois de um reboot — longe de quem poderia entendê-lo.
    """
    for caminho in caminhos:
        if "%" in str(caminho):
            raise AutostartError(
                f"o caminho {caminho} tem '%', que o cmd.exe expande como variável.\n"
                "  Mova o projeto (ou o Python) para um caminho sem '%'."
            )


def conteudo(projeto: Path, python: Path, config: Path | None = None) -> str:
    """O `.cmd` que será escrito. Função pura, para poder ser conferida sem instalar.

    Chama `python -m lanstream.cli` em vez do `lanstream.exe`: o console script
    depende de como o pacote foi instalado, e o módulo funciona em qualquer caso —
    inclusive num `uv pip install -e` que não tenha posto o `Scripts` no PATH.

    O `pause` no fim não é enfeite: se o comando falhar na partida, sem ele a
    janela fecha antes de alguém ler o motivo, e o sintoma vira "não subiu".
    """
    # O `--config` vai explícito, com o caminho resolvido na instalação. Sem ele o
    # sender dependeria de onde o `cd` parou para achar o toml, e um diretório
    # errado não daria erro: cairia nos defaults embutidos e subiria com host,
    # porta e device errados — falha silenciosa depois de um reboot.
    cfg = f' --config "{config}"' if config else ""
    return (
        "@echo off\r\n"
        "rem Gerado por `lanstream install-autostart`.\r\n"
        "rem Para desativar: apague este arquivo, ou rode\r\n"
        "rem   lanstream install-autostart --remove\r\n"
        f'cd /d "{projeto}"\r\n'
        f'"{python}" -m lanstream.cli send --watch{cfg}\r\n'
        "echo.\r\n"
        "echo O sender encerrou. Feche esta janela ou leia o motivo acima.\r\n"
        "pause\r\n"
    )


def alvo() -> Path:
    return pasta_startup() / NOME


def instalar(*, escrever: bool = True) -> tuple[Path, str]:
    """Devolve (caminho, conteúdo). Com `escrever=False` não toca no disco."""
    if not ff.IS_WINDOWS and escrever:
        raise AutostartError(
            "o auto-start é do lado do Windows — é lá que o sender roda.\n"
            "  Para ver o que seria escrito: lanstream install-autostart --dry-run"
        )
    projeto = Path.cwd()
    python = Path(sys.executable)
    _sem_porcento(projeto, python)

    config = find_config_file()
    if config is None and escrever:
        raise AutostartError(
            f"não achei um lanstream.toml a partir de {projeto}.\n"
            "  O auto-start precisa de config explícita: sem ela, o sender subiria\n"
            "  nos defaults embutidos depois de cada reboot — com host, porta e\n"
            "  device errados, e sem reclamar. Rode de dentro do projeto."
        )

    texto = conteudo(projeto, python, config)
    caminho = alvo() if ff.IS_WINDOWS else Path("%APPDATA%") / "…" / "Startup" / NOME
    if escrever:
        try:
            caminho.parent.mkdir(parents=True, exist_ok=True)
            # `mbcs` é a codepage ANSI do Windows: o cmd.exe NÃO lê batch em UTF-8,
            # e um caminho com acento (`C:\Users\João\...`) sairia em mojibake e
            # quebraria o `cd` no login — depois do reboot, longe de quem entenderia.
            codificacao = "mbcs" if ff.IS_WINDOWS else "utf-8"
            caminho.write_text(texto, encoding=codificacao, newline="")
        except (OSError, UnicodeEncodeError) as exc:
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


def alvo_legivel() -> str:
    """O caminho do atalho, ou uma descrição dele quando não se está no Windows."""
    try:
        return str(alvo())
    except AutostartError:
        return "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\" + NOME
