#!/usr/bin/env python3
"""Mede o sincronismo A/V — e ensaia o comando da Fase 3 fora do Windows.

Existem duas perguntas na Fase 3 e elas não são a mesma:

1. **A forma do comando está certa?** Duas entradas, rótulo no filter_complex,
   `-map` explícito, AAC no mesmo MPEG-TS. Isso não depende do ddagrab nem do
   dshow, e por isso dá para responder no Mac — é o modo `ensaio`.
2. **O áudio chega junto com o vídeo?** Isso só o caminho real responde, e a
   resposta precisa ser um número. É o modo `medir`, que lê uma gravação do OBS.

A claquete é uma tela preta que pisca branco por 100 ms a cada 5 s, com um bipe
de 1 kHz nos mesmos 100 ms. Do outro lado, `blackdetect` diz quando o branco
começou e `silencedetect` diz quando o bipe começou; a diferença é a
dessincronia, e a inclinação dela ao longo do arquivo é a deriva. Nada disso
depende de olho nem de ouvido, que é o ponto: "parece sincronizado" não fecha
critério de saída.

    python scripts/av-sync.py ensaio            # monta, roda 20 s e mede, aqui mesmo
    python scripts/av-sync.py claquete c.mp4    # gera o arquivo para tocar no Windows
    python scripts/av-sync.py medir gravacao.mkv --offset-atual 0
"""

from __future__ import annotations

import argparse
import re
import statistics
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from lanstream import config as cfgmod  # noqa: E402
from lanstream import sender  # noqa: E402

PERIOD = 5.0  # segundos entre claquetes
FLASH = 0.1  # duração do branco/bipe

# As vírgulas dentro do `enable` vão escapadas: sem a barra, o parser do
# filtergraph as leria como separador de filtro. Não há aspas aqui de propósito —
# o argv é passado direto ao ffmpeg, sem shell para removê-las.
_WINDOW = rf"lt(mod(t+{PERIOD / 2}\,{PERIOD})\,{FLASH})"
CLAPPER_VIDEO = (
    f"color=c=black:s=1280x720:r=60,drawbox=x=0:y=0:w=iw:h=ih:color=white@1:t=fill:enable={_WINDOW}"
)
CLAPPER_AUDIO = f"sine=frequency=1000:sample_rate=48000,volume=volume=0:enable=not({_WINDOW})"

# Piso de ruído do MÉTODO, não do caminho. O `blackdetect` só pode responder no
# quadro seguinte (17 ms a 60 fps) e o `silencedetect` decide por janelas de ~21
# ms; medido no ensaio local, onde não há dessincronia nenhuma, isso dá uma
# mediana de ~15 ms. Abaixo disso o número não é acionável — e um `-itsoffset`
# de 10 ms seria pura superstição.
RUIDO = 40.0
# Deriva de 1 ms num minuto não se distingue do ruído acima; para o sinal sair da
# medição a janela precisa ser longa. 3 min é o mínimo, 20 é o critério da fase.
DERIVA_MINIMA = 180.0

_BLACK_END = re.compile(r"black_end:(\d+(?:\.\d+)?)")
_SILENCE_END = re.compile(r"silence_end: (\d+(?:\.\d+)?)")


def _run(argv: list[str], *, quiet: bool = False) -> str:
    print("  $ " + " ".join(argv if not quiet else argv[:6] + ["..."]), file=sys.stderr)
    proc = subprocess.run(argv, capture_output=True, text=True, errors="replace")
    return proc.stdout + proc.stderr


# --------------------------------------------------------------------------- #
# Medição
# --------------------------------------------------------------------------- #


@dataclass
class Pair:
    video: float
    audio: float

    @property
    def offset_ms(self) -> float:
        """Positivo = o áudio chegou DEPOIS do vídeo."""
        return (self.audio - self.video) * 1000


def duration(path: Path) -> float:
    """Duração em segundos, ou 0 se o ffprobe não souber dizer."""
    output = _run(
        [
            "ffprobe",
            "-hide_banner",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "compact=p=0:nk=1",
            str(path),
        ]
    )
    try:
        return float(output.strip().splitlines()[0])
    except (ValueError, IndexError):
        return 0.0


def detect(path: Path) -> tuple[list[float], list[float]]:
    """Instantes de cada flash e de cada bipe, em segundos do arquivo.

    O `blackdetect` marca o fim de cada intervalo preto, que é exatamente o
    começo do flash; o `silencedetect` marca o fim de cada silêncio, que é o
    começo do bipe. Os dois escrevem no stderr, e é de lá que sai a medida.

    O fim do arquivo é descartado: os dois filtros fecham o intervalo aberto
    quando a entrada acaba, então um arquivo que termina no preto e no silêncio
    ganha um "flash" e um "bipe" que nunca existiram — e como os dois caem no
    mesmo instante, o par falso passaria por uma medição perfeita e puxaria a
    mediana para o meio do nada.
    """
    fim = duration(path)
    output = _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(path),
            "-vf",
            "blackdetect=d=0.2:pic_th=0.90:pix_th=0.10",
            "-af",
            "silencedetect=noise=-40dB:d=0.2",
            "-f",
            "null",
            "-",
        ]
    )
    corte = fim - FLASH * 2 if fim else float("inf")
    return (
        [t for m in _BLACK_END.findall(output) if (t := float(m)) < corte],
        [t for m in _SILENCE_END.findall(output) if (t := float(m)) < corte],
    )


def pair_up(flashes: list[float], beeps: list[float]) -> list[Pair]:
    """Casa cada bipe com o flash mais próximo, se estiverem a menos de meio período.

    Meio período é o limite que impede o erro clássico desta medição: com uma
    dessincronia grande, o bipe n casaria com o flash n+1 e o resultado sairia
    bonito e errado. Fora dessa janela o par é descartado, e a contagem de pares
    aparece no relatório justamente para que um descarte em massa não passe.
    """
    pairs = []
    for beep in beeps:
        near = min(flashes, key=lambda f: abs(f - beep), default=None)
        if near is not None and abs(near - beep) < PERIOD / 2:
            pairs.append(Pair(video=near, audio=beep))
    return pairs


def report(path: Path, pairs: list[Pair], offset_atual: int) -> int:
    if not pairs:
        print("\nNenhum par claquete encontrado.")
        print("  - O arquivo tem a claquete tocando? (o modo `claquete` gera uma)")
        print("  - A cena do OBS estava com a fonte em tela cheia, sem overlay por cima?")
        return 1

    offsets = [p.offset_ms for p in pairs]
    mediana = statistics.median(offsets)
    print(f"\n{path.name}: {len(pairs)} claquetes")
    print(f"  {'t vídeo':>9} {'t áudio':>9} {'offset':>9}")
    for p in pairs:
        print(f"  {p.video:9.3f} {p.audio:9.3f} {p.offset_ms:+8.1f}ms")

    lado = "áudio atrasado" if mediana > 0 else "áudio adiantado"
    print(f"\n  mediana:  {mediana:+.1f} ms   ({lado})")
    print(f"  faixa:    {min(offsets):+.1f} .. {max(offsets):+.1f} ms")

    # Deriva: o que separa "está 80 ms fora" de "vai estar 400 ms fora no fim da
    # live". A Fase 3 só fecha se esta linha for plana — um offset constante se
    # corrige com uma constante, uma deriva não.
    span = pairs[-1].video - pairs[0].video
    if len(pairs) >= 6 and span >= DERIVA_MINIMA:
        metade = len(pairs) // 2
        deriva = statistics.median(offsets[metade:]) - statistics.median(offsets[:metade])
        por_hora = deriva / span * 3600
        print(f"  deriva:   {deriva:+.1f} ms entre a 1a e a 2a metade ({por_hora:+.0f} ms/hora)")
        if abs(deriva) > RUIDO:
            print("  ^ isto é DERIVA, não offset: -itsoffset não resolve (docs/fase3.md §4)")
    else:
        print(
            f"  deriva:   janela de {span:.0f} s é curta demais para medir "
            f"(precisa de {DERIVA_MINIMA:.0f} s e 6 claquetes)"
        )

    alvo = offset_atual - round(mediana)
    print(f"\n  [audio] offset_ms = {alvo}    # era {offset_atual}, corrige {mediana:+.0f} ms")
    if abs(mediana) < RUIDO:
        print(
            f"  (abaixo de {RUIDO:.0f} ms este método não distingue de zero — "
            "não mexa no offset por causa disto)"
        )
    return 0


# --------------------------------------------------------------------------- #
# Ensaio: o comando da Fase 3 rodando fora do Windows
# --------------------------------------------------------------------------- #


def rehearse_argv(argv: list[str], destino: Path, segundos: int, encoder: str) -> list[str]:
    """Troca as três partes que só existem no Windows, e nada além delas.

    O que sobrevive à troca é o que este ensaio testa: o rótulo `[v]`, os dois
    `-map`, a ordem das flags de entrada do áudio, o `-itsoffset`, o bloco de
    AAC e o mux MPEG-TS. O que é substituído — ddagrab, dshow e NVENC — é
    exatamente o que o Mac não tem, e por isso o ensaio não prova nada sobre eles.
    """
    out = list(argv)

    # 1. o device D3D11 não existe aqui
    i = out.index("-init_hw_device")
    del out[i : i + 2]

    # 2. as duas capturas viram claquete sintética
    i = out.index("-filter_complex")
    out[i + 1] = re.sub(r"^ddagrab[^\[]*", CLAPPER_VIDEO, out[i + 1])
    i = out.index("-f")  # o `-f dshow` da entrada de áudio é o primeiro `-f`
    out[i + 1] = "lavfi"
    j = out.index("-audio_buffer_size")  # opção privada do dshow, sem par no lavfi
    del out[j : j + 2]
    i = out.index("-i")
    out[i + 1] = CLAPPER_AUDIO

    # 3. o NVENC e as flags da família dele viram o encoder local
    inicio, fim = out.index("-c:v"), out.index("-b:v")
    out[inicio:fim] = ["-c:v", encoder]

    # 4. em vez da URL SRT, um arquivo e um tempo — o resto do mux fica igual.
    # O `-y` é do ensaio, não do comando real: a URL SRT nunca pergunta se pode
    # sobrescrever, mas um arquivo pergunta, e com o `-nostdin` que o sender usa
    # a pergunta não tem quem responda — o ffmpeg sai sem escrever nada e a
    # medição sairia do arquivo da rodada anterior, que é o pior erro possível
    # aqui: um número plausível de um teste que não rodou.
    out[-1] = str(destino)
    return [*out[:-3], "-y", "-t", str(segundos), *out[-3:]]


def rehearse(args) -> int:
    cfg = cfgmod.load(Path(args.config) if args.config else None)
    if not cfg.audio.enabled:
        # O ensaio existe para o comando COM áudio; sem isso ele testaria a
        # Fase 2 de novo. O device é fictício de propósito: ele é substituído.
        cfg.audio.enabled = True
        cfg.audio.device = cfg.audio.device or "ensaio (substituído pela claquete)"
    plan = sender.build(cfg)

    destino = Path(args.saida)
    argv = rehearse_argv(plan.argv, destino, args.segundos, args.encoder)
    print("comando da Fase 3, com as três partes do Windows substituídas:\n")
    print("  " + " ".join(plan.argv[:0] or argv))
    print()
    saida = _run(argv)
    if not destino.exists() or destino.stat().st_size == 0:
        print(saida[-2000:])
        return 1

    # Um .ts que existe não prova que tem as duas trilhas: prova que o ffmpeg não
    # abortou. Quem responde é o ffprobe.
    trilhas = _run(
        [
            "ffprobe",
            "-hide_banner",
            "-v",
            "error",
            "-show_entries",
            "stream=index,codec_type,codec_name,channels,sample_rate,r_frame_rate",
            "-of",
            "compact=p=0",
            str(destino),
        ]
    )
    print("\ntrilhas no MPEG-TS gerado:")
    # O ffprobe lista os streams uma vez por programa e uma vez soltos, então num
    # TS de um programa cada trilha aparece duas vezes. Dedup pelo índice.
    for linha in dict.fromkeys(x for x in trilhas.strip().splitlines() if x.strip()):
        print("  " + linha)
    tipos = set(re.findall(r"codec_type=(\w+)", trilhas))
    if not {"video", "audio"} <= tipos:
        print(f"\nFALHA: esperava vídeo E áudio, o arquivo tem {tipos or 'nada'}")
        return 1

    flashes, beeps = detect(destino)
    return report(destino, pair_up(flashes, beeps), cfg.audio.offset_ms)


def clapper(args) -> int:
    """Gera o arquivo de claquete para tocar no Windows durante o teste real."""
    argv = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-f",
        "lavfi",
        "-i",
        CLAPPER_VIDEO.replace("s=1280x720", f"s={args.tamanho}"),
        "-f",
        "lavfi",
        "-i",
        CLAPPER_AUDIO,
        "-t",
        str(args.segundos),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        args.saida,
    ]
    saida = _run(argv)
    destino = Path(args.saida)
    if not destino.exists():
        print(saida[-2000:])
        return 1
    print(f"\n{destino} — {destino.stat().st_size / 1e6:.1f} MB, {args.segundos}s")
    print(f"Um flash branco de {FLASH * 1000:.0f} ms + bipe de 1 kHz a cada {PERIOD:.0f} s.")
    print("Toque em tela cheia no Windows, com o som saindo pelo device capturado.")
    return 0


def measure(args) -> int:
    path = Path(args.arquivo)
    if not path.exists():
        print(f"não encontrei {path}")
        return 1
    flashes, beeps = detect(path)
    print(f"\n{len(flashes)} flashes, {len(beeps)} bipes")
    return report(path, pair_up(flashes, beeps), args.offset_atual)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("ensaio", help="roda o comando da Fase 3 no Mac, com claquete sintética")
    e.add_argument("--config", default="")
    e.add_argument("--segundos", type=int, default=20)
    e.add_argument("--saida", default="/tmp/lanstream-ensaio.ts")
    e.add_argument("--encoder", default="h264_videotoolbox", help="o encoder LOCAL do ensaio")
    e.set_defaults(func=rehearse)

    c = sub.add_parser("claquete", help="gera o vídeo de claquete para tocar no Windows")
    c.add_argument("saida")
    c.add_argument("--segundos", type=int, default=1260, help="21 min cobre o teste de 20")
    c.add_argument("--tamanho", default="1920x1080")
    c.set_defaults(func=clapper)

    m = sub.add_parser("medir", help="mede offset e deriva numa gravação do OBS")
    m.add_argument("arquivo")
    m.add_argument("--offset-atual", type=int, default=0, dest="offset_atual")
    m.set_defaults(func=measure)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
