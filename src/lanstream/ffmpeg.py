"""Localizar o ffmpeg e perguntar do que ele é capaz.

Duas lições da Fase 0 moram aqui:

* **A versão importa.** O ffmpeg 9.0.1 exige driver NVIDIA >= 610.00 e quebra o
  NVENC com o 591.74 instalado (baseline §2). Por isso a versão é extraída e
  exposta, não só impressa.
* **O ffmpeg do Homebrew não tem libsrt** (baseline §1). No Mac o preview passa
  por `srt-live-transmit`; quem checa `-protocols` e conclui "SRT ausente, está
  quebrado" está errado — no Mac isso é o esperado.
"""

from __future__ import annotations

import functools
import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

IS_WINDOWS = platform.system() == "Windows"
IS_MACOS = platform.system() == "Darwin"

# Consultados depois do PATH. Existem porque o instalador do ffmpeg no Windows
# nem sempre atualiza o PATH da sessão aberta — sintoma clássico de "instalei e
# o doctor não acha".
KNOWN_DIRS: tuple[Path, ...] = (
    tuple(
        Path(p)
        for p in (
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links",
            Path(r"C:\ffmpeg\bin"),
            Path(r"C:\Program Files\ffmpeg\bin"),
        )
    )
    if IS_WINDOWS
    else (Path("/opt/homebrew/bin"), Path("/usr/local/bin"), Path("/usr/bin"))
)


def _parse_listing(output: str) -> set[str]:
    """Nomes de uma listagem `-encoders` / `-filters`.

    O formato é: legenda das flags, uma linha `------`, e só então as linhas de
    verdade (`V....D h264_nvenc  NVIDIA...`, ` .. scale  V->V  ...`). Cortar na
    separação é o que sobrevive à largura do campo de flags mudar — no ffmpeg 8.x
    o `-filters` imprime 2 caracteres onde o `-encoders` imprime 6, e uma regex de
    largura fixa erra em silêncio: a versão anterior deste código casava só com a
    linha da legenda e concluía que o `ddagrab` não existia.
    """
    parts = re.split(r"^\s*-{3,}\s*$", output, maxsplit=1, flags=re.MULTILINE)
    body = (
        parts[1]
        if len(parts) > 1
        else "\n".join(
            # Build sem separador: a legenda é o que tem "=", as entradas não têm.
            line
            for line in output.splitlines()
            if "=" not in line
        )
    )
    names = set()
    for line in body.splitlines():
        # Toda entrada é indentada; cabeçalhos ("Encoders:") não são.
        if line[:1].strip():
            continue
        fields = line.split()
        if len(fields) >= 2:
            names.add(fields[1])
    return names


class FFmpegError(Exception):
    """Falha ao localizar ou interrogar o ffmpeg — mensagem já pronta para o usuário."""


def find_binary(name: str, override: str = "") -> Path | None:
    """config > PATH > locais conhecidos. Devolve None se não achar em lugar nenhum."""
    if override:
        path = Path(override)
        return path if path.exists() else None

    found = shutil.which(name)
    if found:
        return Path(found)

    suffix = ".exe" if IS_WINDOWS else ""
    for directory in KNOWN_DIRS:
        candidate = directory / f"{name}{suffix}"
        if candidate.exists():
            return candidate
    return None


def _run(binary: Path, *args: str) -> str:
    """Roda o ffmpeg e devolve stdout+stderr. O ffmpeg escreve em stderr por padrão."""
    try:
        proc = subprocess.run(
            [str(binary), "-hide_banner", *args],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=30,
        )
    except OSError as exc:
        raise FFmpegError(f"não consegui executar {binary}: {exc}") from None
    except subprocess.TimeoutExpired:
        raise FFmpegError(f"{binary} não respondeu em 30 s") from None
    return proc.stdout + proc.stderr


@dataclass
class FFmpegInfo:
    """O que este ffmpeg específico sabe fazer."""

    path: Path
    version: str
    build: str

    def raw(self, *args: str) -> str:
        """Saída crua (stdout+stderr) de uma consulta a este ffmpeg.

        Existe para as consultas que não cabem num `set[str]` — hoje só a
        listagem de devices dshow, que precisa da ordem e das linhas de "nome
        alternativo" para ser lida direito. Não é cacheada: a lista de devices
        muda quando alguém pluga um cabo, e o `doctor --audio` é rodado
        justamente depois de instalar um driver novo.
        """
        return _run(self.path, *args)

    @functools.cached_property
    def encoders(self) -> set[str]:
        return _parse_listing(_run(self.path, "-encoders"))

    @functools.cached_property
    def filters(self) -> set[str]:
        return _parse_listing(_run(self.path, "-filters"))

    @functools.cached_property
    def protocols(self) -> set[str]:
        # "Supported file protocols:" / "Input:" / "  file" / "Output:" / ...
        return {
            line.strip()
            for line in _run(self.path, "-protocols").splitlines()
            if line.strip() and not line.rstrip().endswith(":")
        }

    @property
    def version_tuple(self) -> tuple[int, ...]:
        """(9, 0, 1) a partir de "9.0.1".

        Vazio quando não é uma versão numerada — os builds de git do gyan.dev se
        chamam `2026-01-01-git-abcdef`, e ler "2026" como número de versão faria
        qualquer comparação de "é mais novo que" mentir.
        """
        match = re.fullmatch(r"(\d+)\.(\d+)(?:\.(\d+))?", self.version)
        return tuple(int(g) for g in match.groups() if g) if match else ()


def probe(binary: Path) -> FFmpegInfo:
    """Roda `-version` e extrai versão e build. Não consulta encoders (isso é lazy)."""
    output = _run(binary, "-version")
    first = output.splitlines()[0] if output else ""
    match = re.search(r"ffmpeg version (\S+)", first)
    if not match:
        raise FFmpegError(f"{binary} não parece ser o ffmpeg — respondeu: {first[:80]!r}")
    raw = match.group(1)
    # "8.1-full_build-www.gyan.dev" -> versão "8.1", build "full_build-www.gyan.dev".
    # Um build de git ("2026-01-01-git-abcdef") não tem versão: fica inteiro no
    # campo, e `version_tuple` devolve vazio para quem for comparar.
    semver = re.match(r"^(\d+\.\d+(?:\.\d+)?)-?(.*)$", raw)
    version, build = semver.groups() if semver else (raw, "")
    return FFmpegInfo(path=binary, version=version, build=build)


def load(override: str = "") -> FFmpegInfo:
    binary = find_binary("ffmpeg", override)
    if binary is None:
        hint = (
            "  winget install --id=Gyan.FFmpeg.Shared -e  (e reabra o terminal, pelo PATH)"
            if IS_WINDOWS
            else "  brew install ffmpeg"
        )
        raise FFmpegError(f"ffmpeg não encontrado no PATH nem nos locais conhecidos.\n{hint}")
    return probe(binary)
