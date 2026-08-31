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

# O console do Windows abre em cp1252, e as marcas ✅/❌ deste script não cabem
# nela: o `conferir` imprimia o diagnóstico inteiro e morria com UnicodeEncodeError
# na última linha — a que diz o VIÉS a ser usado na comparação. Pior que perder a
# linha, o script saía com traceback e código != 0, então quem o usasse dentro de
# outro script leria "a claquete não presta" quando ela prestava. É o mesmo defeito
# que o `_run` do ffmpeg.py tinha ao contrário: assumir que o encoding do console é
# o encoding do texto. Aqui a saída é forçada a UTF-8 nas duas plataformas.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

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

# `pic_th` é a fração de pixels escuros que faz o `blackdetect` chamar o quadro de
# preto — e os dois valores úteis falham em cenários opostos, medido em 31/08:
#
#   0.98 (o default do ffmpeg): acha o flash mesmo com a fonte ocupando 6% da
#         cena, mas QUALQUER overlay claro permanente acima de 2% da tela faz o
#         quadro nunca ser preto, e aí não há um flash sequer.
#   0.90: aguenta um overlay de 5%, mas exige que o flash cubra >10% da tela —
#         com a fonte pequena na cena, encontra os bipes e nenhum flash.
#
# Nenhum dos dois serve de default sozinho, então o `detect_com_fallback` tenta o
# sensível e cai para o tolerante quando o primeiro volta vazio. Descobrir isso
# custaria a rodada inteira: o sintoma só aparece DEPOIS dos 20 min de gravação.
PIC_TH_SENSIVEL = 0.98
PIC_TH_TOLERANTE = 0.90

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


def bipes_por_tom(path: Path, flashes: list[float]) -> list[float]:
    """Acha os bipes filtrando a banda de 1 kHz antes de decidir o que é silêncio.

    Existe para o caminho ACÚSTICO (`docs/obs-setup.md` §4), em que o bipe da
    claquete chega pelo ar até o microfone: ele sai a −23 dB de pico sobre um
    ruído de quarto em −50, e o `silencedetect` cru ora vê 10 bipes ora vê 56,
    conforme o limiar. O tom é puro e o ruído é de banda larga, então filtrar
    antes separa os dois — medido em 31/08: 19 bipes contra 18 flashes, com
    cadência de 4,99 s.

    O limiar não é fixo porque o nível depende do volume e da distância; são
    tentados vários e vence o que produzir a contagem mais perto do número de
    flashes, que é quantos bipes devem existir. Isso é possível aqui e não no
    caminho normal justamente porque o vídeo diz a resposta.
    """
    melhor: list[float] = []
    for limiar in (-45, -50, -55, -60, -65):
        saida = _run(
            [
                "ffmpeg",
                "-hide_banner",
                "-i",
                str(path),
                "-af",
                f"bandpass=f=1000:width_type=h:w=100,silencedetect=noise={limiar}dB:d=0.2",
                "-f",
                "null",
                "-",
            ]
        )
        achados = [float(m) for m in _SILENCE_END.findall(saida)]
        if not melhor or abs(len(achados) - len(flashes)) < abs(len(melhor) - len(flashes)):
            melhor, escolhido = achados, limiar
    print(f"  banda de 1 kHz: {len(melhor)} bipes com noise={escolhido}dB")
    return melhor


def detect(path: Path, pic_th: float = PIC_TH_SENSIVEL) -> tuple[list[float], list[float]]:
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
            f"blackdetect=d=0.2:pic_th={pic_th}:pix_th=0.10",
            "-af",
            "silencedetect=noise=-40dB:d=0.2",
            "-f",
            "null",
            "-",
        ]
    )
    flashes = [float(m) for m in _BLACK_END.findall(output)]
    beeps = [float(m) for m in _SILENCE_END.findall(output)]
    if not fim:
        # Sem duração (ffprobe dizendo N/A, gravação truncada) o corte por tempo
        # não existe — e cair para "não filtra nada" seria o pior dos dois mundos,
        # porque o par falso do fim cai nos dois filtros no mesmo instante e
        # passaria por uma medição perfeita. Descartar o último de cada lista
        # custa no máximo um par bom e nunca deixa entrar um inventado.
        print("  (ffprobe não deu a duração: descartando o último flash e o último bipe)")
        return flashes[:-1], beeps[:-1]
    corte = fim - FLASH * 2
    return ([t for t in flashes if t < corte], [t for t in beeps if t < corte])


def detect_com_fallback(path: Path, pic_th: float = 0.0) -> tuple[list[float], list[float]]:
    """`detect` com o segundo limiar como rede, quando o primeiro não vê flash.

    `pic_th` explícito desliga a rede: quem passou um valor quer aquele valor.
    """
    if pic_th:
        return detect(path, pic_th)
    flashes, beeps = detect(path, PIC_TH_SENSIVEL)
    if flashes:
        return flashes, beeps
    print(f"  nenhum flash com pic_th={PIC_TH_SENSIVEL}; tentando {PIC_TH_TOLERANTE}")
    print("  (é o que acontece com overlay claro fixo na cena — ver av-sync.py §pic_th)")
    return detect(path, PIC_TH_TOLERANTE)


# Quanto um par pode se afastar do deslocamento de consenso e ainda ser a mesma
# claquete. Uma claquete boa varia pelo quantum do quadro (17 ms a 60 fps) mais a
# janela do silencedetect (~21 ms); 50 ms cobre isso com folga e continua muito
# menor que o espaçamento entre claquetes.
TOLERANCIA_MS = 50.0


def consenso(flashes: list[float], beeps: list[float]) -> float | None:
    """O deslocamento em que o maior número de flashes acha um bipe.

    A captura real não entrega silêncio entre as claquetes: ela entrega o que a
    máquina estiver tocando, e qualquer coisa acima do limiar vira um
    `silence_end`. Em 31/08 uma gravação de 20 s com 4 claquetes trouxe 13 bipes.

    Escolher "o bipe mais próximo de cada flash" erra nessa situação, e erra em
    silêncio: um espúrio a 200 ms do flash ganha do verdadeiro a 125 ms. O que os
    espúrios não conseguem é *concordar entre si* — eles estão espalhados, e as
    claquetes verdadeiras estão todas no mesmo deslocamento, porque é o mesmo
    caminho que as produziu.

    Então o deslocamento é decidido por votação: cada par (flash, bipe) plausível
    é um voto, e vence a janela de ±TOLERANCIA que recolher mais votos de flashes
    distintos. É o mesmo princípio de um RANSAC de uma dimensão só.
    """
    votos = sorted((b - f) * 1000 for f in flashes for b in beeps if abs(b - f) < PERIOD / 2)
    if not votos:
        return None
    melhor, melhor_n = None, 0
    for centro in votos:
        dentro = [v for v in votos if abs(v - centro) <= TOLERANCIA_MS]
        if len(dentro) > melhor_n:
            melhor, melhor_n = statistics.median(dentro), len(dentro)
    return melhor


def pair_up(flashes: list[float], beeps: list[float]) -> list[Pair]:
    """Um par por FLASH: para cada flash, o bipe mais próximo dentro de meio período.

    Meio período é o limite que impede o erro clássico desta medição: com uma
    dessincronia grande, o bipe n casaria com o flash n+1 e o resultado sairia
    bonito e errado. Fora dessa janela o par é descartado, e a contagem de pares
    aparece no relatório justamente para que um descarte em massa não passe.

    A direção importa, e a versão anterior a tinha errada — iterava sobre os
    bipes. O flash é o evento confiável: ele só existe se um quadro branco chegou.
    O bipe não: qualquer falha do áudio (um clique, um vão de buffer, um
    underrun) interrompe o silêncio e o `silencedetect` reporta um `silence_end`
    que não é claquete nenhuma. Medido em 31/08 no loopback do Mac, uma gravação
    de 78 s com 16 claquetes produziu 30 pares, com a faixa indo a ±2,4 s — os
    artefatos entravam todos como medida. Iterando sobre os flashes há no máximo
    um par por claquete, e o excedente vira o diagnóstico do `report`.
    """
    desloc = consenso(flashes, beeps)
    if desloc is None:
        return []
    alvo = desloc / 1000
    pairs = []
    for flash in flashes:
        # O bipe mais próximo do deslocamento de consenso — não do flash.
        near = min(beeps, key=lambda b: abs(b - flash - alvo), default=None)
        if near is not None and abs(near - flash - alvo) * 1000 <= TOLERANCIA_MS:
            pairs.append(Pair(video=flash, audio=near))
    return pairs


def report(
    path: Path,
    pairs: list[Pair],
    offset_atual: int,
    flashes: list[float] | None = None,
    beeps: list[float] | None = None,
) -> int:
    flashes, beeps = flashes or [], beeps or []
    if not pairs:
        print("\nNenhum par claquete encontrado.")
        if beeps and not flashes:
            # Esta combinação é específica e vale nomear: o áudio chegou, então o
            # caminho inteiro funciona — quem não foi visto foi o flash.
            print(f"  {len(beeps)} bipes e NENHUM flash: o áudio chegou, o branco não foi visto.")
            print("  - a fonte está pequena na cena? o flash precisa cobrir >2% da tela")
            print("  - há overlay claro fixo por cima? tente --pic-th 0.90 (ou 0.80)")
        elif flashes and not beeps:
            print(f"  {len(flashes)} flashes e NENHUM bipe: o vídeo chegou, o áudio não.")
            print("  - é o F3.3 falhando, não a medição: o device não está entregando som")
        else:
            print("  - O arquivo tem a claquete tocando? (o modo `claquete` gera uma)")
            print("  - A gravação pegou a cena certa?")
        return 1

    offsets = [p.offset_ms for p in pairs]
    mediana = statistics.median(offsets)
    print(f"\n{path.name}: {len(pairs)} claquetes")
    # Cobertura: que fração dos flashes achou bipe no deslocamento de consenso.
    # Um consenso forte casa quase todos; um fraco é ruído que por acaso se
    # alinhou, e sem esta linha ele imprimiria uma mediana com cara de medida. A
    # gravação contaminada de 31/08 12:16 — em que o tom da claquete não estava
    # na trilha — casou 9 de 26 flashes e "mediu" +1472 ms.
    cobertura = len(pairs) / len(flashes) if flashes else 0
    if flashes:
        print(f"  cobertura: {len(pairs)}/{len(flashes)} flashes ({cobertura:.0%})")
    if cobertura < 0.7:
        print(
            "  ❌ CONSENSO FRACO: menos de 70% dos flashes acharam bipe. O número\n"
            "     abaixo provavelmente é ruído que se alinhou por acaso — confira se a\n"
            "     claquete está mesmo no áudio (av-sync.py conferir) antes de usá-lo."
        )
    # Bipe a mais que flash é falha no áudio, não claquete: cada clique ou vão de
    # buffer interrompe o silêncio e o silencedetect o reporta. Não corrompe mais
    # a medida (ver pair_up), mas continua sendo sintoma e por isso é dito.
    extras = len(beeps) - len(pairs)
    if beeps and extras > max(1, len(pairs) // 10):
        print(
            f"  ⚠️  {extras} bipes além das claquetes: o áudio tem falhas "
            "(clique, vão de buffer, underrun) — não é dessincronia, é continuidade"
        )
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
        # A `deriva` é a distância entre as MEDIANAS das duas metades, e elas não
        # estão separadas pela janela inteira: estão separadas pelos centros das
        # metades, que é ~metade dela. Dividir pelo `span` daria metade da taxa
        # real — e como o F3.4 decide a fase em "> 100 ms/hora", uma rodada que
        # devia reprovar leria como aprovada. O denominador é medido, não
        # deduzido, para valer também com claquete faltando no meio.
        centro = statistics.median([p.video for p in pairs[metade:]]) - statistics.median(
            [p.video for p in pairs[:metade]]
        )
        por_hora = deriva / centro * 3600 if centro else 0.0
        print(f"  deriva:   {deriva:+.1f} ms entre a 1a e a 2a metade ({por_hora:+.0f} ms/hora)")
        if abs(deriva) > RUIDO:
            print("  ^ isto é DERIVA, não offset: -itsoffset não resolve (docs/fase3.md §4)")
        elif centro:
            # A taxa em ms/hora é uma extrapolação: quem foi medido é a diferença
            # entre as metades, e ela tem o piso de ruído do método. Numa janela
            # curta, uma taxa alta pode ser só ruído multiplicado — dizer "deriva
            # de 300 ms/hora" a partir de 15 ms medidos seria inventar precisão.
            print(
                f"  ^ diferença dentro do ruído ({RUIDO:.0f} ms): esta janela só "
                f"resolve deriva acima de {RUIDO / centro * 3600:.0f} ms/hora"
            )
    else:
        print(
            f"  deriva:   janela de {span:.0f} s é curta demais para medir "
            f"(precisa de {DERIVA_MINIMA:.0f} s e 6 claquetes)"
        )

    # O `offset_atual` é premissa, não medida — e o valor de verdade está no
    # lanstream.toml do WINDOWS, não no da máquina que roda esta medição. Ler o
    # config local seria pior que perguntar: daria um número plausível e errado.
    # Então a premissa vai impressa, para que uma segunda rodada com o offset já
    # corrigido não recomende sobrescrever a correção com um valor absoluto.
    alvo = offset_atual - round(mediana)
    print(f"\n  premissa: [audio] offset_ms = {offset_atual} no toml DO WINDOWS", end="")
    print(" — se não for esse, passe --offset-atual" if not offset_atual else "")
    print(f"  [audio] offset_ms = {alvo}    # era {offset_atual}, corrige {mediana:+.0f} ms")
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
    print("  " + " ".join(argv))
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

    flashes, beeps = detect_com_fallback(destino)
    return report(destino, pair_up(flashes, beeps), cfg.audio.offset_ms, flashes, beeps)


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


def conferir(args) -> int:
    """A claquete deste arquivo presta? Roda antes de gravar, não depois.

    Existe por causa da rodada de 31/08: o vídeo da claquete chegou perfeito no
    Mac e o áudio não chegou nunca, e a diferença entre "o arquivo nasceu mudo" e
    "o Windows não está tocando o som dele" custou duas gravações para aparecer.
    Este modo responde a primeira metade sozinho, na máquina que tem o arquivo.
    """
    path = Path(args.arquivo)
    if not path.exists():
        print(f"não encontrei {path}")
        return 1

    trilhas = _run(
        [
            "ffprobe",
            "-hide_banner",
            "-v",
            "error",
            "-show_entries",
            "stream=index,codec_type,codec_name,channels,sample_rate",
            "-of",
            "compact=p=0",
            str(path),
        ]
    )
    tipos = set(re.findall(r"codec_type=(\w+)", trilhas))
    print(f"\n{path.name}")
    for linha in dict.fromkeys(x for x in trilhas.strip().splitlines() if x.strip()):
        print("  " + linha)

    if "audio" not in tipos:
        print("\n❌ o arquivo NÃO TEM trilha de áudio — a claquete nasceu muda.")
        print("   Gere de novo:  python scripts/av-sync.py claquete claquete.mp4 --segundos 1260")
        return 1
    if "video" not in tipos:
        print("\n❌ o arquivo não tem trilha de vídeo.")
        return 1

    dur = duration(path)
    esperado = int(dur / PERIOD) if dur else 0
    flashes, beeps = detect_com_fallback(path, args.pic_th)
    print(
        f"\n  {len(flashes)} flashes e {len(beeps)} bipes em {dur:.0f} s"
        f"  (esperado ~{esperado} de cada)"
    )

    if not beeps:
        print("\n❌ a trilha de áudio existe mas está VAZIA — nenhum bipe.")
        print("   É defeito na geração, não na reprodução. Gere de novo.")
        return 1
    if not flashes:
        print("\n❌ nenhum flash: a trilha de vídeo não tem a claquete.")
        return 1

    pares = pair_up(flashes, beeps)
    if not pares:
        print("\n❌ há flashes e bipes, mas eles não se casam — o arquivo não presta.")
        return 1
    mediana = statistics.median([p.offset_ms for p in pares])
    print(f"  {len(pares)} claquetes casadas, mediana {mediana:+.1f} ms")
    print(f"\n✅ o arquivo presta. Guarde a mediana: ela é o VIÉS do método ({mediana:+.0f} ms),")
    print("   e é com ela que a medição da gravação deve ser comparada — não com zero.")
    if abs(len(beeps) - esperado) > max(2, esperado // 5):
        print("\n⚠️  a contagem de bipes destoa do esperado; confira se o arquivo está inteiro.")
    return 0


def measure(args) -> int:
    path = Path(args.arquivo)
    if not path.exists():
        print(f"não encontrei {path}")
        return 1
    flashes, beeps = detect_com_fallback(path, args.pic_th)
    if args.tom:
        beeps = bipes_por_tom(path, flashes)
    print(f"\n{len(flashes)} flashes, {len(beeps)} bipes")
    return report(path, pair_up(flashes, beeps), args.offset_atual, flashes, beeps)


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

    v = sub.add_parser("conferir", help="a claquete deste arquivo presta? (rode ANTES de gravar)")
    v.add_argument("arquivo")
    v.add_argument("--pic-th", type=float, default=0.0, dest="pic_th")
    v.set_defaults(func=conferir)

    m = sub.add_parser("medir", help="mede offset e deriva numa gravação do OBS")
    m.add_argument("arquivo")
    m.add_argument("--offset-atual", type=int, default=0, dest="offset_atual")
    m.add_argument(
        "--tom",
        action="store_true",
        help="acha os bipes pela banda de 1 kHz — para o áudio captado pelo MICROFONE",
    )
    m.add_argument(
        "--pic-th",
        type=float,
        default=0.0,
        dest="pic_th",
        help=f"limiar do blackdetect; 0 = tenta {PIC_TH_SENSIVEL} e cai para {PIC_TH_TOLERANTE}",
    )
    m.set_defaults(func=measure)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
