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
from . import autostart as autostart_mod
from . import doctor as doctor_mod
from . import logs as logs_mod
from . import receiver as receiver_mod
from . import sender as sender_mod
from . import supervisor as supervisor_mod
from .autostart import AutostartError
from .config import Config, ConfigError, find_config_file
from .config import load as load_config
from .encoders import EncoderError
from .ffmpeg import FFmpegError
from .receiver import ReceiverError
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
    except (
        ConfigError,
        FFmpegError,
        EncoderError,
        SenderError,
        ReceiverError,
        AutostartError,
    ) as exc:
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
def doctor(
    config: ConfigOption = None,
    audio: Annotated[
        bool,
        typer.Option(
            "--audio", help="Só a lista de devices DirectShow (o nome para [audio] device)."
        ),
    ] = False,
) -> None:
    """Diagnostica este lado: ffmpeg, encoders, captura, áudio, SRT, rede e firewall."""
    sys.exit(_guard(doctor_mod.run, _load(config), audio))


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
    no_audio: Annotated[
        bool,
        typer.Option("--no-audio", help="Ignora o [audio] desta rodada: só vídeo, como na Fase 2."),
    ] = False,
    watch: Annotated[
        bool,
        typer.Option("--watch", help="Fica no ar: reergue o ffmpeg sozinho quando ele cair."),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Guarda no log TODAS as linhas de progresso, não só a amostra de 30s.",
        ),
    ] = False,
) -> None:
    """Captura a tela do Windows e publica em SRT. Ctrl+C encerra."""
    cfg = _load(config)
    if bitrate:
        cfg.video.bitrate = bitrate
        _guard(cfg.video.validate)
    # Desligar o áudio devolve exatamente o comando da Fase 2, e é assim que se
    # decide de quem é a culpa quando a rodada com áudio quebra: se sem áudio
    # funciona, o problema é o device, não a captura nem a rede.
    if no_audio:
        cfg.audio.enabled = False

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
        + "\nCtrl+C encerra."
        + ("\n--watch ligado: o sender se reergue sozinho quando cair." if watch else ""),
        fg="green",
    )

    # O log é aberto aqui, depois de o comando estar montado e antes de subir o
    # ffmpeg: assim a primeira linha do arquivo é sempre o comando que rodou, que
    # é a primeira coisa que se quer saber ao reler.
    destino = logs_mod.caminho_padrao(cfg.logs.dir)
    diario = logs_mod.configurar(
        destino, max_mb=cfg.logs.max_mb, manter=cfg.logs.manter, verbose=verbose
    )
    if diario is None:
        typer.secho(f"aviso: não consegui escrever em {destino} — seguindo sem log.", fg="yellow")
    else:
        typer.secho(f"  log em {destino}", fg="cyan")
        diario.info("=== sessão iniciada (watch=%s) ===", watch)
        diario.info("comando: %s", plan.shell_line)
        for linha in sender_mod.summary(cfg, plan):
            diario.info("%s", linha)
    batimento = logs_mod.Batimento(cfg.logs.batimento_s)

    def _registrar(linha: str, progresso: bool) -> None:
        """O que vai para o console vai também para o arquivo — o progresso, por amostragem."""
        _echo_ffmpeg(linha, progresso)
        if diario is None:
            return
        if not progresso:
            diario.info("%s", linha)
        elif batimento.passa():
            diario.info("[batimento] %s", linha)
        else:
            # As linhas de progresso entre uma amostra e outra só entram com
            # `--verbose`, que liga o nível DEBUG. É o que a flag faz: trocar o
            # batimento pelo registro completo, para quando se está caçando um
            # engasgo de segundos e a amostra de 30 s é grossa demais.
            diario.debug("%s", linha)

    def _anunciar(mensagem: str) -> None:
        # Mensagem do supervisor, não do ffmpeg: cor diferente e sempre em linha
        # nova, para não se confundir com a linha de progresso que se reescreve.
        with _ECHO_LOCK:
            if _echo_ffmpeg.pending:
                typer.echo("")
                _echo_ffmpeg.pending = False
        typer.secho("[watch] " + mensagem, fg="yellow")
        if diario is not None:
            diario.warning("[watch] %s", mensagem.replace("\n", " | "))

    if watch:
        sessao = _guard(supervisor_mod.supervisionar, cfg, plan, _registrar, _anunciar)
        typer.echo("")
        for linha in sessao.resumo():
            typer.secho("  " + linha, fg="cyan")
            if diario is not None:
                diario.info("resumo: %s", linha)
        raise typer.Exit(0)

    resultado = _guard(sender_mod.run, plan, _registrar)
    if diario is not None:
        diario.info("saiu com %s: %s", resultado.code, resultado.motivo)
    if resultado.motivo and not resultado.interrompido:
        typer.secho(f"  o ffmpeg saiu: {resultado.motivo}", fg="yellow")
        if resultado.reiniciar:
            typer.secho("  (--watch reergueria sozinho)", fg="yellow")
    # 255 é como o ffmpeg reporta "recebi SIGINT e saí" — encerramento pedido pelo
    # usuário não é falha, e sair 255 daqui faria um script de sessão achar que foi.
    raise typer.Exit(0 if resultado.code in (0, 255) else 1)


@app.command()
def receive(
    config: ConfigOption = None,
    preview: Annotated[
        bool, typer.Option("--preview/--no-preview", help="Abre a janela do ffplay (padrão).")
    ] = True,
    host: Annotated[str, typer.Option("--host", help="Sobrescreve o IP do sender.")] = "",
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Só imprime os comandos montados.")
    ] = False,
) -> None:
    """Recebe o stream e mostra numa janela — o diagnóstico 'é a rede ou é o OBS?'."""
    cfg = _load(config)
    plan = _guard(lambda: receiver_mod.build(cfg, host=host))

    typer.secho(f"  conectando em {plan.url}", fg="cyan")
    typer.echo("")
    typer.echo(plan.shell_line)
    typer.echo("")
    if dry_run:
        return

    # A recusa vem antes do aviso: dizer "o OBS vai cair" e sair sem abrir socket
    # nenhum informaria um estrago que não aconteceu.
    if not preview:
        typer.secho("--no-preview ainda não tem outro modo; use --dry-run.", fg="red", err=True)
        raise typer.Exit(2)

    # O aviso vem antes de conectar porque depois já é tarde: o listener do
    # sender atende UM cliente, e tomar essa vaga derruba o OBS sem avisar
    # ninguém do outro lado (docs/windows.md §4).
    typer.secho(
        "Atenção: isto consome a conexão única do sender. Se o OBS estiver\n"
        "pegando o stream, ele vai cair — e o sender precisa ser reiniciado depois.",
        fg="yellow",
    )

    code = _guard(receiver_mod.run, plan, lambda m: typer.secho(m, fg="yellow", err=True))
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


@app.command("install-autostart")
def install_autostart(
    remove: Annotated[
        bool, typer.Option("--remove", help="Apaga o atalho em vez de criá-lo.")
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Mostra o que seria escrito, sem escrever.")
    ] = False,
) -> None:
    """Faz o `send --watch` subir sozinho no login do Windows."""
    if remove and dry_run:
        # Quem aprendeu que --dry-run não toca no disco esperaria o mesmo aqui, e
        # apagar mesmo assim seria a pior traição possível dessa expectativa.
        typer.secho(f"seria removido: {autostart_mod.alvo_legivel()}", fg="green")
        return
    if remove:
        caminho = _guard(autostart_mod.remover)
        typer.secho(f"removido: {caminho}" if caminho else "não havia nada instalado.", fg="green")
        return

    caminho, texto = _guard(lambda: autostart_mod.instalar(escrever=not dry_run))
    typer.secho(f"{'seria escrito em' if dry_run else 'instalado em'} {caminho}", fg="green")
    if "--config" not in texto:
        # Só acontece no --dry-run: a instalação de verdade recusa. Mas um preview
        # que mostra um comando sem --config sem dizer nada ensinaria o errado.
        typer.secho(
            "aviso: sem lanstream.toml no diretório atual, o comando sai sem --config —\n"
            "  depois de um reboot ele subiria nos defaults embutidos, sem reclamar.\n"
            "  Rode de dentro do projeto.",
            fg="yellow",
        )
    typer.echo("")
    for linha in texto.replace("\r\n", "\n").rstrip().splitlines():
        typer.echo("  " + linha)
    typer.echo("")
    if not dry_run:
        typer.secho(
            "Vale no próximo login. Para desfazer: lanstream install-autostart --remove", fg="cyan"
        )


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
