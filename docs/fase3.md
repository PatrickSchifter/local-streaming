# Fase 3 — Áudio do jogo (Windows)

O ponto mais chato do projeto, e a fase que começa com um buraco de hardware: o
`win-doctor` da Fase 0 registrou **nenhum device dshow nesta máquina** — nem
microfone, nem loopback (`baseline.md` §7). Não é um problema de código, e nenhum
código o resolve.

O que dá para fazer daqui, e foi feito, é chegar nesse buraco com tudo o mais
pronto: o comando montado, a mensagem de erro que aponta o caminho, e uma medição
de sincronismo que não depende de ouvido. O que falta é instalar um device no
Windows e rodar o §F3 do [`proximos-testes.md`](proximos-testes.md).

Data: 2026-08-30

---

## 1. Por que precisa de um device intermediário, e qual

O `ffmpeg` **não tem** captura WASAPI loopback no Windows. O que ele tem é
DirectShow (`-f dshow`), e o DirectShow só enxerga *devices de captura* — coisas
que o Windows apresenta como entrada. A saída do sistema não é uma delas. Alguém
precisa expor "o que está tocando" como se fosse um microfone.

A restrição que ordena as opções não é técnica, é de quem joga: **o áudio precisa
continuar saindo pela caixa de som do Windows**, porque quem está jogando está
sentado nela. Uma solução que captura o áudio e o tira do jogador não serve, por
mais limpa que seja.

| Opção | Custo de instalação | O jogador continua ouvindo? | Risco |
|---|---|---|---|
| **1. Mixagem estéreo (Stereo Mix)** do Realtek | nenhum — é só habilitar | sim, sem nada no caminho | pode não existir no driver; o nível costuma seguir o volume mestre |
| **2. VB-CABLE** | driver + reboot | **só com "Ouvir este dispositivo"**, que acrescenta latência ao que o jogador ouve | a latência do "Ouvir" pode atrapalhar o jogo |
| **3. VoiceMeeter** | driver + reboot + configurar mixer | sim, é para isso que ele existe | mais peça para dar errado no meio da live |
| **4. `virtual-audio-capturer`** | registrar uma DLL | sim, não mexe no roteamento | projeto parado desde ~2018 |

A ordem de tentativa é essa, e o motivo de o Stereo Mix vir primeiro é que ele
custa dois minutos e pode encerrar a fase: `Som > Gravação > botão direito >
Mostrar dispositivos desativados`. O Windows o esconde desabilitado por padrão,
não ausente — a lista do `Win32_SoundDevice` que o baseline consultou **não
mostraria** um Stereo Mix desabilitado, então "esta máquina não tem loopback"
ainda pode ser falso. É a primeira coisa que o §F3.1 manda conferir.

O PLANO listava o VB-CABLE em primeiro e o `virtual-audio-capturer` em segundo.
A ordem mudou aqui por causa da restrição do parágrafo acima: o VB-CABLE sozinho
**cala o jogo para quem está jogando**, e a correção ("Ouvir este dispositivo")
é justamente o que põe latência no ouvido do jogador. Ele continua na lista, mas
depois do que não tem esse efeito colateral.

## 2. O comando: com áudio muda de forma, sem áudio não muda nada

Com `[audio] enabled = false` o argv sai **byte a byte igual** ao que a Fase 2
mediu no Windows — verificado com `diff` contra a saída do commit anterior. Isso
não é elegância: é o que faz do `--no-audio` um bisect de verdade. Se a rodada com
áudio quebrar, `lanstream send --no-audio` volta exatamente ao comando que já
passou, e a resposta a "é o áudio ou é outra coisa?" custa uma tecla.

Com o áudio ligado entram quatro coisas, nesta ordem:

```
-filter_complex ddagrab=0:framerate=60[v]        <- a saída do filtro ganha nome
-f dshow -audio_buffer_size 50 -thread_queue_size 1024 -i "audio=<device>"
-map [v] -map 0:a                                <- as duas trilhas, na mão
-c:a aac -b:a 160k -ar 48000 -ac 2
```

| Trecho | Por quê |
|---|---|
| `[v]` + `-map` | Com uma segunda entrada no comando, deixar a seleção automática decidir é apostar num comportamento que muda entre versões do ffmpeg. Rótulo e mapa explícitos não têm ambiguidade. |
| `-map 0:a` | O áudio é a **única** entrada de arquivo: o vídeo nasce dentro do `filter_complex`, sem `-i`. Por isso o dshow é o input 0, e não 1. |
| `-audio_buffer_size 50` | O default do dshow é o do device, "tipicamente algum múltiplo de 500 ms" (docs do ffmpeg). Meio segundo de áudio atrasado não é detalhe de latência: é a dessincronia inteira, de graça. |
| `-thread_queue_size 1024` | Duas entradas ao vivo: a que for lida mais devagar enche a fila, e o ffmpeg passa de avisar a descartar pacote. |
| `-ar 48000 -ac 2` | 48 kHz é o que o MPEG-TS e o OBS esperam; forçar estéreo evita descobrir na live que o device era mono. |
| `-itsoffset` (só se `offset_ms`) | Opção de **entrada**: desloca os timestamps deste input. No bloco de saída não corrigiria nada. |

## 3. O ensaio: a forma do comando testada sem sair do Mac

`python scripts/av-sync.py ensaio` pega o argv que o `sender.build()` produz e
troca **só as três partes que não existem fora do Windows** — `ddagrab` vira uma
claquete sintética, `dshow` vira `lavfi`, o NVENC vira `h264_videotoolbox` — e
grava num arquivo em vez da URL SRT. Tudo o que sobrevive à troca é o que o
ensaio testa: o rótulo, os dois `-map`, a ordem das flags de entrada, o
`-itsoffset`, o bloco de AAC e o mux MPEG-TS.

Resultado de 30/08, 200 s:

```
trilhas no MPEG-TS gerado:
  index=0|codec_name=h264|codec_type=video|r_frame_rate=60/1
  index=1|codec_name=aac|codec_type=audio|sample_rate=48000|channels=2

40 claquetes
  mediana:  +10.7 ms      faixa: +1.3 .. +20.0 ms
  deriva:   -0.0 ms entre a 1a e a 2a metade (-0 ms/hora)
```

**O que isto prova:** o comando com duas trilhas é aceito, as duas chegam no TS
com os parâmetros pedidos, e o mux não introduz deriva.
**O que não prova:** nada sobre o `ddagrab`, o dshow ou o NVENC — que é
exatamente onde a Fase 3 pode falhar. O ensaio derruba as falhas baratas antes de
alguém ir até a outra máquina; não substitui a ida.

### O sinal do `-itsoffset`, medido em vez de presumido

Errar o sinal aqui dobraria a dessincronia em vez de zerá-la, e o erro seria
plausível o bastante para durar uma noite. Com `offset_ms = 200` no ensaio, a
medição deu **+210.7 ms** (os 200 pedidos + o viés de ~11 do método). Portanto:

> **`offset_ms` positivo ATRASA o áudio.** Se o som chega adiantado, o valor é
> positivo; se chega atrasado, negativo.

## 4. Como o sincronismo é medido — e qual é o piso do método

A claquete é uma tela preta que pisca branco por 100 ms a cada 5 s, com um bipe
de 1 kHz nos mesmos 100 ms. Do outro lado, `blackdetect` diz quando o branco
começou, `silencedetect` diz quando o bipe começou, e a diferença é a
dessincronia. Nada de olho nem de ouvido: "parece sincronizado" não fecha
critério de saída.

Três coisas que a medição precisa dizer e que o script já trata:

1. **O método tem viés.** O `blackdetect` só pode responder no quadro seguinte
   (17 ms a 60 fps) e o `silencedetect` decide por janelas de ~21 ms. Medindo o
   **próprio arquivo de claquete**, que é perfeito por construção, sai `+12 ms`.
   Por isso o piso é 40 ms: abaixo disso o número não é acionável, e um
   `-itsoffset` de 10 ms seria superstição.
2. **Offset e deriva são defeitos diferentes.** Offset constante se corrige com
   uma constante; deriva, não — ela vem de dois relógios diferentes (o do
   `ddagrab` e o do device de áudio) e a correção seria `aresample=async=1`, que é
   assunto da Fase 7 e com medição junto. Por isso o relatório separa os dois, e
   só calcula deriva com janela de 3 min ou mais: em 20 s, ruído vira "274 ms/hora".
   E a **taxa** em ms/hora é extrapolação — o que foi medido é a diferença entre
   as metades, com o piso de ruído junto. Uma janela de 20 min separa os centros
   das metades por 10 min, então ela só resolve deriva acima de ~240 ms/hora; o
   script imprime esse limite em vez de anunciar precisão que não tem.
   *(O denominador dessa conta é a distância entre os centros das metades, não a
   janela inteira — a revisão pegou esse fator 2, e ele fazia uma rodada que devia
   reprovar no §F3.4 ler como aprovada.)*
3. **O fim do arquivo mente.** Os dois filtros fecham o intervalo aberto quando a
   entrada acaba, então um arquivo que termina no preto e no silêncio ganha um
   "flash" e um "bipe" que nunca existiram — e como caem no mesmo instante, o par
   falso passaria por uma medição perfeita. São descartados.

4. **O offset atual é premissa, e ela mora na outra máquina.** A medição roda no
   Mac; o `[audio] offset_ms` que ela corrige está no `lanstream.toml` do
   **Windows**. Ler o config local daria um número plausível e errado, então o
   script imprime a premissa que usou — sem isso, a segunda rodada do laço
   "corrige e confirma" recomendaria sobrescrever a correção anterior com um valor
   absoluto, e o laço nunca convergiria.

O mesmo script gera a claquete para tocar no Windows (`claquete`) e mede uma
gravação do OBS (`medir`), o que fecha o laço: o número que sai da gravação vira
a linha `[audio] offset_ms = N` pronta para colar.

## 5. O que o doctor passou a responder

- `lanstream doctor --audio` lista os devices dshow **classificados**: `loopback`,
  `microfone` ou `desconhecido`, palpite pelo nome, loopback primeiro. Sem device
  nenhum, ele imprime a ordem de tentativa do §1 em vez de só dizer "nenhum".
- O diagnóstico completo ganhou a linha de áudio, inclusive quando ele está
  desligado — "por que não tem som?" se pergunta no meio da live, e a resposta
  mais provável é `enabled = false`. Um doctor calado sobre isso manda procurar
  no lugar errado.
- Device configurado que não está na lista vira FALHA **com a lista junto**; e um
  nome que só erra por caixa ou acento é diagnosticado à parte, porque o dshow
  abre pelo nome literal e "quase certo" ali não é certo.
- Um device cujo nome não parece de loopback passa, com aviso: o que iria ao ar
  seria o ambiente do quarto, não o jogo.

O parser da listagem aguenta os dois formatos que existem (`"Nome" (audio)` do
ffmpeg 5+ e as seções `DirectShow audio devices` até o 4.4), verificado contra
amostras dos dois — é o mesmo erro que o commit aacb863 consertou no `-encoders`,
e ele custaria um "nenhum device de áudio" numa máquina cheia deles.

## 6. A revisão de código: sete defeitos, e um deles decidia a fase errado

O `/code-review` rodou sobre o commit e achou sete — nenhum crítico, todos reais,
todos corrigidos. Os quatro que valem registro:

1. **A taxa de deriva saía pela metade** (fator 2 no denominador, §4). O §F3.4
   decide a fase em cima desse número: uma rodada que devia reprovar leria como
   aprovada. É o pior tipo de defeito que este projeto pode ter — um instrumento
   que erra para o lado de "está tudo bem", como os dois defaults que a revisão da
   Fase 2 pegou.
2. **O doctor inteiro morria se o `-encoders` travasse.** A checagem de áudio lia
   `info.encoders` fora do `_ask`; com o ffmpeg pendurado, o `check_ffmpeg` já
   tinha registrado a FALHA e voltado, mas a leitura seguinte levantava de novo e
   o relatório saía pelo `_guard` **antes de ser impresso** — exatamente no
   cenário que o módulo existe para diagnosticar.
3. **`doctor --audio` saía 0 sem device nenhum**, contra a convenção do módulo
   (código 1 se houve FALHA, para dar `doctor && send`). E ainda mandava "cole o
   nome exato" embaixo de uma lista vazia.
4. **Um microfone configurado como captura passava em verde.** `[ OK ]` num
   device de microfone é o ambiente do quarto no ar em vez do jogo, e um OK não
   aparece no resumo final. Virou AVISO — não FALHA, porque a classificação é
   palpite pelo nome e um device legítimo de nome esquisito não pode barrar a
   transmissão.

Os outros três: o descarte do par falso do fim do arquivo se desligava sozinho
quando o `ffprobe` não dava a duração (agora descarta o último evento, que erra
para o lado seguro); o `--offset-atual` era uma premissa silenciosa (§4.4); e
sobrou um `plan.argv[:0] or argv` que era sempre a segunda metade.

## 7. O que falta, e o que é bloqueio

| | |
|---|---|
| ✅ | argv com áudio, `--no-audio`, config (`buffer_ms`, `offset_ms`), doctor, medição |
| ✅ | forma do comando validada num ffmpeg real (ensaio local) |
| 🔴 | **um device de captura no Windows** — sem isso não há o que testar |
| 🔴 | §F3 no Windows: device, A/V sync medido, 20 min sem deriva |

O bloqueio é o device. Todo o resto está pronto para a primeira rodada.
