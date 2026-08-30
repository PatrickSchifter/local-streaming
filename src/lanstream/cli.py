"""Entrada da CLI. Fase 1 entregou `doctor` e `config`, a Fase 2 traz o `send`;
`receive` e `obs` chegam nas Fases 4 e 6.

Regra que vale para todos os comandos: erro de config ou de ambiente sai como
mensagem de uma linha e código 2 — nunca como traceback (PLANO §Fase 1).
"""

from __future__ import annotations

import sys
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import typer

from . import __version__
from . import doctor as doctor_mod
from . import sender as sender_mod
from .config import Config, ConfigError, find_config_file
from .config import load as load_config
from .encoders import EncoderError
from .ffmpeg import FFmpegError
from .sender import SenderError

app = typer.Typer(
    add_completion=False,
    help="Streaming de jogo pela LAN: Windows -> Mac -> OBS -> Twitch.",
)
config_app = typer.Typer(no_args_is_help=True, help="Inspecionar a configuração efetiva.")
app.add_typer(config_app, name="config")

ConfigOption = Annotated[
    Path | None,
    typer.Option("--config", "-c", help="Arquivo TOML explícito (pula a cadeia de busca)."),
]


def _load(path: Path | None) -> Config:
    try:
        return load_config(path)
    except ConfigError as exc:
        typer.secho(f"erro de configuração: {exc}", fg="red", err=True)
        raise typer.Exit(2) from None


def _guard(fn, *args):
    """Rede de segurança: erro conhecido vira uma linha, nunca um traceback.

    O doctor já trata o que consegue tratar; isto pega o que escapar de um
    caminho novo, para que a promessa da Fase 1 não dependa de disciplina.
    """
    try:
        return fn(*args)
    except (ConfigError, FFmpegError, EncoderError, SenderError) as exc:
        typer.secho(f"erro: {exc}", fg="red", err=True)
        raise typer.Exit(2) from None


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    version: Annotated[bool, typer.Option("--version", help="Imprime a versão e sai.")] = False,
) -> None:
    if version:
        typer.echo(f"lanstream {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


@app.command()
def doctor(config: ConfigOption = None) -> None:
    """Diagnostica este lado: ffmpeg, encoders, captura, SRT, rede e firewall."""
    sys.exit(_guard(doctor_mod.run, _load(config)))


@app.command()
def send(
    config: ConfigOption = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Só imprime o comando montado, não executa.")
    ] = False,
    encoder: Annotated[
        str, typer.Option("--encoder", help="Força o encoder (ex.: hevc_nvenc). Ignora a cadeia.")
    ] = "",
    bitrate: Annotated[
        str, typer.Option("--bitrate", help='Sobrescreve o bitrate do vídeo (ex.: "12M").')
    ] = "",
) -> None:
    """Captura a tela do Windows e publica em SRT. Ctrl+C encerra."""
    cfg = _load(config)
    if bitrate:
        cfg.video.bitrate = bitrate
        _guard(cfg.video.validate)

    note = _guard(sender_mod.check_platform, dry_run)
    # Fora do Windows o ffmpeg local não é o que vai rodar: exigir que ele exista
    # transformaria "me mostre o comando" numa dependência de ambiente.
    plan = _guard(sender_mod.plan_for, cfg, encoder, not note)

    if note:
        typer.secho(note, fg="yellow", err=True)
    for line in sender_mod.summary(cfg, plan):
        typer.secho("  " + line, fg="cyan")
    typer.echo("")
    typer.echo(plan.shell_line)
    typer.echo("")

    if dry_run:
        return

    typer.secho(
        "No Mac: Media Source no OBS com "
        + cfg.network.url_for_ffmpeg(mode="caller", host=cfg.network.host or "<ip-deste-pc>")
        + "\nCtrl+C encerra.",
        fg="green",
    )
    code = _guard(sender_mod.run, plan, _echo_ffmpeg)
    # 255 é como o ffmpeg reporta "recebi SIGINT e saí" — encerramento pedido pelo
    # usuário não é falha, e sair 255 daqui faria um script de sessão achar que foi.
    raise typer.Exit(0 if code in (0, 255) else 1)


# No encerramento há duas fontes escrevendo no console ao mesmo tempo: a thread
# que drena o stderr do ffmpeg e o próprio `_shutdown`, que anuncia o que está
# fazendo. Sem o lock as duas linhas se intercalam no meio e o `pending` fica
# desatualizado, colando a próxima linha na de progresso — e isso aconteceria em
# todo Ctrl+C, que é o caminho que o usuário sempre vê.
_ECHO_LOCK = threading.Lock()


def _echo_ffmpeg(line: str, is_progress: bool) -> None:
    """Progresso se reescreve na mesma linha; o resto rola normalmente."""
    with _ECHO_LOCK:
        if is_progress:
            typer.echo(f"\r{line}", nl=False)
        else:
            typer.echo(("\n" if _echo_ffmpeg.pending else "") + line)
        _echo_ffmpeg.pending = is_progress


_echo_ffmpeg.pending = False


@config_app.command("show")
def config_show(config: ConfigOption = None) -> None:
    """Imprime a config efetiva — defaults já aplicados — e de onde ela veio."""
    cfg = _load(config)
    typer.echo(f"# origem: {cfg.source or 'defaults embutidos (nenhum arquivo encontrado)'}")
    for section, values in asdict(cfg).items():
        if not isinstance(values, dict):
            continue
        typer.echo(f"\n[{section}]")
        for key, value in values.items():
            rendered = (
                f'"{value}"'
                if isinstance(value, str)
                else str(value).lower()
                if isinstance(value, bool)
                else value
            )
            typer.echo(f"{key} = {rendered}")


@config_app.command("path")
def config_path() -> None:
    """Mostra a cadeia de busca e qual arquivo venceu."""
    from .config import CONFIG_FILENAME, USER_CONFIG

    winner = find_config_file()
    for candidate in (Path.cwd() / CONFIG_FILENAME, USER_CONFIG):
        mark = "->" if candidate == winner else "  "
        state = "existe" if candidate.exists() else "ausente"
        typer.echo(f"{mark} {candidate}  ({state})")
    if winner is None:
        typer.echo("-> nenhum arquivo: valem os defaults embutidos")


if __name__ == "__main__":
    app()
