"""Entrada da CLI. Fase 1 entrega `doctor` e `config`; `send`/`receive`/`obs`
chegam nas Fases 2, 4 e 6.

Regra que vale para todos os comandos: erro de config ou de ambiente sai como
mensagem de uma linha e código 2 — nunca como traceback (PLANO §Fase 1).
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import typer

from . import __version__
from . import doctor as doctor_mod
from .config import Config, ConfigError, find_config_file
from .config import load as load_config
from .ffmpeg import FFmpegError

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
    except (ConfigError, FFmpegError) as exc:
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
