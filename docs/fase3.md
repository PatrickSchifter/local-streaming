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

### O que essa tabela não dizia: o Stereo Mix é do Realtek, não do sistema

Habilitar a Mixagem estéreo desta máquina não resolveu, e a razão não está em
nenhuma coluna acima. O Stereo Mix espelha a mistura da placa **onboard**; aqui o
único endpoint de reprodução ativo é a "TV PHILCO" na *NVIDIA High Definition
Audio* (HDMI), e todo endpoint Realtek está NOTPRESENT ou UNPLUGGED. O jogo sai
pelo HDMI, o Stereo Mix escuta o Realtek: são caminhos diferentes, e nenhum ajuste
de volume junta os dois.

Medido com `-af volumedetect`, 3 s, com o GTA tocando:

| Device | mean | max |
|---|---|---|
| `virtual-audio-capturer` | −29,0 dB | −11,4 dB |
| `Mixagem estéreo (Realtek …)` | −90,3 dB | −76,3 dB |

O Stereo Mix **abre** (`rc 0`, stereo 44,1 kHz) e entrega silêncio — é o modo de
falha caro, porque não parece falha em lugar nenhum: o device existe, o doctor o
lista como loopback, o ffmpeg não reclama, e o silêncio só aparece do outro lado.
Por isso a linha 1 da tabela ganha uma pré-condição: *o Stereo Mix só serve se a
saída padrão do Windows for a placa que tem o Stereo Mix*. Com o áudio indo para
um monitor ou TV por HDMI/DisplayPort — que é o caso desta máquina — ele está fora
antes de ser testado, e o `virtual-audio-capturer` sobe para primeiro por
capturar o endpoint padrão seja ele qual for.

Quem for conferir isso de novo: `Som > Reprodução` mostra qual é o dispositivo
padrão, e é o nome dele que precisa bater com a placa do Stereo Mix. Um
`volumedetect` de 3 s com som tocando responde a mesma pergunta sem abrir nada.

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

4. **A cena do OBS decide se o flash é visto.** O `blackdetect` chama um quadro
   de preto quando uma fração `pic_th` dos pixels está escura, e os dois valores
   úteis falham em cenários opostos — medido em 31/08 contra gravações `.mkv`
   montadas como o OBS as grava:

   | cena | `pic_th=0.98` | `pic_th=0.90` |
   |---|---|---|
   | fonte em tela cheia | 13 flashes | 13 flashes |
   | fonte a 50% da largura | 13 | 13 |
   | fonte a 25% (6% da área) | 13 | **1** |
   | overlay claro fixo de 5% | **0** | 13 |

   Com o limiar tolerante, uma fonte pequena na cena dá **bipes e nenhum flash**;
   com o sensível, qualquer overlay claro permanente acima de 2% da tela faz o
   quadro nunca ser preto e o resultado é o mesmo. Como nenhum dos dois serve de
   default sozinho, o script tenta o sensível e cai para o tolerante quando o
   primeiro volta vazio — e `--pic-th` desliga a rede para quem quiser mandar.

   Isso importa pelo momento em que apareceria: o sintoma só existe **depois** dos
   20 minutos de gravação, quando refazer custa outros 20. Foi encontrado testando
   a medição contra um `.mkv` recodificado em vez do `.ts` que o próprio script
   gera — o formato que a Fase 3 vai medir de verdade nunca tinha sido usado.

5. **A mensagem de "nenhum par" agora separa as causas.** `bipes sem flash` é
   cena; `flashes sem bipe` não é medição nenhuma, é o F3.3 falhando — o áudio não
   está chegando, e mandar mexer na cena seria mandar caçar a coisa errada.

6. **O offset atual é premissa, e ela mora na outra máquina.** A medição roda no
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
| ✅ | **um device de captura no Windows** — `virtual-audio-capturer`, medido com o jogo tocando |
| ✅ | §F3.1–F3.3 no Windows: device, doctor, som no OBS — rodados em 31/08 (§8) |
| 🔴 | §F3.4: a mediana do A/V sync sobre uma gravação, e 20 min sem deriva |

**O bloqueio do device caiu em 31/08.** Com o GTA aberto, o
`virtual-audio-capturer` entrega mean −29,0 dB / max −11,4 dB em 48 kHz estéreo —
a taxa que o `encode_args` já pede, então nem resample entra no caminho. A
Mixagem estéreo, testada no mesmo minuto, deu silêncio pelo motivo do §1: ela é
do Realtek e a saída desta máquina é HDMI. Não há device a instalar; o que falta
é rodar a coisa inteira contra o Mac e medir o offset com o `scripts/av-sync.py`.
O que a rodada de 31/08 produziu, incluindo um atraso de 2–3 s que **não** era do
sender, está no §8.

## 8. A rodada de 31/08 no Windows: o que passou, e onde o atraso **não** estava

Primeira vez com device real na máquina do Windows. F3.1, F3.2 e F3.3 passaram;
o número do F3.4 ainda não existe.

| passo | resultado |
|---|---|
| F3.1 device | `virtual-audio-capturer` — mean −29,0 dB / max −11,4 dB com o GTA tocando, 48 kHz estéreo |
| F3.2 doctor | tudo OK, zero AVISO; `device de áudio: "virtual-audio-capturer" (loopback)` |
| F3.3 som no OBS | **sai som do jogo** — as duas trilhas no mux, `Stream #0:1: Audio: aac (LC), 48000 Hz, stereo, 160 kb/s` |
| F3.4 mediana / deriva | 🔴 **não medido** |
| F3.5 fps / bitrate | parcial: 60 fps, `speed` 0,995–0,997x, 15,6 Mbps *com* áudio, sem `Thread message queue blocking` |

### O atraso de 2–3 s, e por que ele não é do sender

O F3.3 veio com um sintoma: no Mac, **a imagem chegava 2–3 s antes do áudio**.
Isso é grande demais para o `-itsoffset`, que trabalha em dezenas de ms — e a
tentação era mexer no `offset_ms` até "ficar bom". Em vez disso, dois `start_time`:

| onde | video | audio | Δ |
|---|---|---|---|
| `.ts` gravado direto do pipeline, sem rede | 1,421333 | 1,400000 | **21 ms** |
| o mesmo stream **depois de ir e voltar pelo SRT** | 1,421333 | 1,400000 | **21 ms** |

Idênticos. **O mux nasce alinhado e o SRT não desalinha.** Os 21 ms estão dentro
do piso do §4, e o que sobra é o lado do Mac.

O teste do SRT precisou de uma porta diferente da 9000, e o motivo é a regra 1:
o OBS do Mac reconecta sozinho a cada 2 s e **já tinha tomado a conexão única**
do listener — o caller local levou `I/O error` sem o sender ter nada de errado.
Quem repetir isto: use outra porta em vez de concluir que o listener quebrou.

**O que fica registrado como regra:** `offset_ms` corrige o *sender*, e o sender
está certo. Antes de escrever qualquer número nele, meça os dois `start_time` —
um `-itsoffset` de 2500 ms "consertaria" pelo ouvido o que a medição mostra
alinhado, e o F3.4 seguinte acusaria a coisa errada.

### O que ainda não está respondido

Depois de mexerem no OBS do Mac, o relato foi de que **ficou sincronizado** — mas
isso é ouvido, não medição, e o ouvido não distingue a gravação do caminho de
**monitoração** do OBS, que tem latência própria e não entra no `.mkv`. O
critério do F3.4 continua sendo a mediana sobre a gravação, e ele é o que falta.

---

## 9. O loopback do Mac: o caminho de cá, medido sem a outra máquina

O §8 provou que o sender entrega alinhado — 21 ms, antes e depois do SRT — e que
o atraso de 2–3 s nasce deste lado. Faltava dizer **onde**, e para isso não era
preciso o Windows: dá para reproduzir o caminho inteiro aqui.

Montagem de 31/08, 12:06: claquete ao vivo (`hevc_videotoolbox` 15M + AAC 160k,
o mesmo perfil do sender) → `srt-live-transmit` em modo **listener** na 9100 →
uma cena e uma fonte temporárias no OBS, criadas por `obs-websocket` **copiando
as configurações da fonte real** (`buffering_mb=2`, `hw_decode=True`,
`input_format=mpegts`) → gravação → medição. Tudo removido no fim.

### 9.1 O que foi medido, e o que ele responde

```
14 claquetes em 78 s de gravação sadia
  mediana:  -12.9 ms      12 das 14 dentro de ±21 ms
```

Contra o viés de **+12 ms** do método (§4), isso é **alinhado** — a diferença de
~25 ms está dentro do piso de 40 ms. Portanto:

> **O caminho do Mac não introduz dessincronia sistemática.** Media Source →
> mixer → gravação sai alinhado, com as mesmas configurações da fonte real.

O que sobra para explicar os 2–3 s ouvidos no F3.3 é o **caminho de monitoração**,
e a evidência apareceu ao ler o OBS ao vivo em vez do arquivo de cena: o
`monitorType` no disco (29/08) era `Monitor Off` e o valor **em execução** era
`MONITOR_AND_OUTPUT` — ou seja, foi ligado naquele dia. A monitoração tem
latência própria e **não entra no `.mkv`**, que é exatamente a ressalva que o §8
levantou. O `Sync Offset` estava em 0, a fonte não estava muda, e o log não tinha
uma linha de `audio buffering` sequer naquela sessão.

> ⚠️ **O arquivo de cena mente sobre o presente.** O OBS só grava o
> `basic/scenes/*.json` ao sair ou ao trocar de coleção; com o OBS aberto desde
> 29/08, o que está no disco é o que ele **carregou**, não o que está valendo. Quem
> for conferir configuração de fonte pergunte por `obs-websocket`.

### 9.2 O buffer de áudio do OBS é *sticky* — e isso é risco de sessão

Quando o script matou o sender local, o log registrou:

```
adding 938 milliseconds of audio buffering, total audio buffering is now 960 ms
```

O OBS sobe esse buffer sozinho quando os timestamps chegam trêmulos ou o stream
seca, e ele **não desce**: só zera reiniciando a fonte. Não foi o que aconteceu no
F3.3 (o log daquela sessão não tem a linha), mas é o mecanismo que produziria
exatamente aquele sintoma — e um engasgo de rede no meio de uma live deixaria até
um segundo de atraso permanente no áudio. **Se o áudio "atrasar sozinho" durante
uma sessão, a ação é reiniciar a fonte, não mexer no `offset_ms`.** Vale procurar
essa linha no log antes de qualquer outra hipótese.

### 9.3 O instrumento pareava na direção errada

A gravação trouxe bipes que não eram claquete: 78 s com 16 flashes produziram
**30 pares**, com a faixa indo a ±2,4 s. A causa era o `pair_up` iterar sobre os
**bipes** — cada clique, vão de buffer ou underrun interrompe o silêncio, o
`silencedetect` reporta um `silence_end`, e aquilo entrava como medida.

O flash é o evento confiável: ele só existe se um quadro branco chegou. Iterando
sobre os flashes há no máximo um par por claquete, e os mesmos dados passaram de
30 pares com faixa de ±2,4 s para **14 pares, mediana −12,9 ms, faixa de −298 a
−2 ms**. O excedente de bipes virou diagnóstico impresso — ele não é
dessincronia, é **continuidade**: áudio com falha.

Isto teria estragado a medição do F3.4 sem dar sinal: a mediana sobreviveu aqui
por sorte estatística, e num arquivo com mais artefatos ela não sobreviveria.

### 9.4 O que isto NÃO prova

O sender do teste é local: um MacBook Air fanless encodando 1080p60, servindo
SRT, decodificando e gravando **ao mesmo tempo**. Os artefatos de áudio das
9.3 podem ser dessa disputa e não do caminho real. O que o teste isola é a
**geometria** — offset entre as trilhas —, não a continuidade. Quem responde sobre
continuidade é o F3.4 com o sender do Windows, e agora ele avisa quando há bipe a
mais.

## 10. O F3.4 do lado do Windows: o áudio sai daqui, e sai sincronizado

A rodada das 12:16 gravou no Mac **vídeo perfeito e áudio nenhum**, e a pergunta
que sobrou foi de que lado o áudio se perdia. As três medidas abaixo foram feitas
nesta máquina, sem o Mac, e fecham o lado de cá.

**1. O arquivo de claquete presta.** `av-sync.py conferir claquete.mp4`:

```
252 flashes e 252 bipes em 1260 s  (esperado ~252 de cada)
252 claquetes casadas, mediana +10.7 ms
```

**2. O capturador ouve os bipes.** `silencedetect` sobre o
`virtual-audio-capturer` com a claquete tocando, `silence_end` em 4,843 / 9,835 /
14,848 s — intervalos de 4,99 e 5,01 s, que é a cadência de 5 s da claquete. Não
é média de volume, é a batida certa no relógio certo.

**3. E o pipeline inteiro entrega as duas trilhas casadas.** 60 s gravados com o
argv **idêntico** ao do `send`, só trocando o SRT por arquivo:

```
12 flashes e 12 bipes em 60 s  (esperado ~12 de cada)
12 claquetes casadas, mediana -0.3 ms
```

Contra o viés de +10,7 ms do próprio arquivo, **−0,3 ms**. O ddagrab, o
`virtual-audio-capturer`, o hevc_nvenc, o AAC e o mux MPEG-TS entregam áudio e
vídeo alinhados dentro do ruído do método.

**O que isso elimina:** não é a claquete, não é o device, não é o encoder, não é
o mux, e (pelo §8) não é o SRT. O áudio existe no fio. O que falta explicar está
entre o fio e o `.mkv` do OBS.

**A hipótese que sobra, e ela é verificável:** no F3.3 o áudio **foi ouvido** no
OBS, e no F3.4 ele não estava na gravação. Ouvir e gravar são caminhos diferentes
no OBS — a trilha da fonte precisa estar atribuída à **track que está sendo
gravada** (em `Saída > Modo Avançado > Gravação`, as tracks são escolhidas a
dedo). Uma fonte audível cuja trilha não está na track gravada produz exatamente
este sintoma: vídeo perfeito, áudio zero, e nenhum erro em lugar nenhum.

### O `conferir` morria no console do Windows

Ele imprimia o diagnóstico inteiro e quebrava na última linha — a que diz o viés —
com `UnicodeEncodeError` no `✅`, porque o console do Windows abre em cp1252. Pior
que perder a linha: saía com traceback e código != 0, então quem chamasse o
`conferir` de dentro de outro script leria "a claquete não presta" **justamente
quando ela presta**. É o mesmo defeito que o `_run` do `ffmpeg.py` tinha ao
contrário (§ commit 305559a): confundir o encoding do console com o encoding do
texto. A saída do script agora é forçada a UTF-8 nas duas plataformas.


---

## 10. O que a rodada de 31/08 estabeleceu, e o que eu conclui demais

Os dois lados mediram, e as duas medições são boas. Só uma leitura foi longe
demais, e é a minha.

**Estabelecido, das duas pontas:**

| | |
|---|---|
| o arquivo de claquete presta | 252 flashes / 252 bipes em 1260 s, viés +10,7 ms (Windows) |
| o capturador ouve os bipes | `silence_end` a 4,843 / 9,835 / 14,848 s — cadência de 5 s no relógio |
| o pipeline do sender entrega alinhado | 60 s com o argv do `send`, SRT trocado por arquivo: mediana −0,3 ms contra viés +10,7 |
| o áudio da claquete **chega** no Mac | 12:42, 4 de 4 claquetes, tom 35 dB acima do fundo na banda de 1 kHz |
| o OBS mede atraso sozinho | `audio is lagging (over by 2490.16 ms) at max audio buffering. Restarting source audio` (12:34) |

**Onde eu conclui demais.** Anunciei "é deriva, não offset" apoiado numa medição
de **27% de cobertura** (+2167 ms) mais aquela linha do log. Tratei as duas como
confirmação independente do mesmo número — e não são: a linha é das 12:34, de uma
sessão anterior à reconexão das 12:39, e a medição é de outra. Das quatro
gravações do dia, **uma só** passa no portão de cobertura que eu mesmo tinha
acabado de escrever:

| gravação | cobertura | mediana |
|---|---|---|
| 12:23:16 | 50% | −523 ms |
| **12:42:04** | **100%** | **+120 ms** |
| 12:45:13 | 50% | −1227 ms |
| 12:45:59 | 27% | +2167 ms |

Um instrumento que acabei de dotar de um aviso de confiabilidade não serve de
nada se quem o lê ignora o aviso no primeiro resultado interessante.

**Duas leituras minhas que o Windows corrigiu, e ele está certo:**

* Li `−48 dB` como "device parado". O piso real daquela máquina é −91 dB, e −48 dB
  é o que um `volumedetect` devolve quando a média inclui 5 s de silêncio para
  cada 100 ms de bipe. Um sinal de 2% de *duty cycle* sempre parece silêncio numa
  média — quem decide é o `silencedetect`.
* Disse que "outro som afogou a claquete". Não havia outro som; o que eu li como
  textura de música no espectrograma era piso de ruído renderizado numa escala
  larga. O GTA estava na tela e mudo.

O que continua **de pé** da minha parte é o mais estreito: na gravação das 12:16 o
tom de 1 kHz não estava lá (medido na banda, nos instantes dos flashes, que é
imune ao duty cycle), e na das 12:42 estava. As duas coisas são verdade, e é isso
que a próxima rodada tem de explicar.

### O que decide

A cobertura desaba junto com o atraso, e isso tem uma explicação testável: o OBS
**reinicia o áudio da fonte** quando o atraso passa do buffer máximo — está no log,
duas vezes hoje. Reinício no meio da gravação come pedaços do áudio, e pedaço
faltando é exatamente o que derruba a cobertura.

Para separar emissor de receptor falta **uma gravação longa do lado do Windows**:
o mesmo teste de 60 s que já passou, mas de 8 a 10 minutos, medido no começo e no
fim. Sessenta segundos são curtos demais para um atraso que leva minutos para
aparecer — do mesmo jeito que o `start_time` do §8 era curto demais por ser um
instante só.


---

## 11. F3.4 medido: o atraso é constante, e o valor não é estável entre rodadas

Gravação de 31/08 13:11, 654 s com a claquete em tela cheia o tempo inteiro —
a primeira do dia em que o material dura a janela toda:

```
101 claquetes, cobertura 101/132 flashes (77%)
  mediana:  +231,4 ms      faixa: +203,5 .. +256,0 ms
  deriva:   -2,9 ms entre as metades (-29 ms/hora)
  por terços: +231,4 / +223,4 / +235,4 ms
```

**Não há deriva.** Onze minutos, 101 medidas, e os três terços variam ±6 ms —
bem abaixo do piso de 40 ms do método. O atraso é constante dentro da janela,
logo é *offset*: `-itsoffset` corrige, e o `aresample=async=1` que o §10 deixava
em aberto não é necessário. Isso fecha a pergunta que a rodada anterior abriu.

### O que ainda não fecha

O valor **mudou entre rodadas da mesma conexão**:

| gravação | cursor da fonte | claquetes | cobertura | mediana |
|---|---|---|---|---|
| 12:42:04 | — | 4 | 100% | +120,5 ms |
| 12:56:00 (só 35 s úteis) | 982 s | 6 | 75% | +112,2 ms |
| **13:11:04** | 1886 s | **101** | 77% | **+231,4 ms** |

Não houve reconexão entre a segunda e a terceira: o cursor foi de 982 s para
1886 s continuamente. Dentro de cada janela o valor é estável; entre elas, dobrou.
Não há explicação medida para isso, e as hipóteses (o buffer do OBS acomodando em
degraus, o conteúdo da tela mudando o comportamento do encoder) não foram
testadas — ficam como hipótese, não como causa.

> **A gravação das 12:56 rendeu 35 s de 11 minutos**, porque a claquete saiu da
> tela e o desktop entrou. Isso se vê nos quadros extraídos, não no relatório: a
> medição não sabe dizer que a fonte parou de mostrar a claquete, só que os
> flashes acabaram. Quem for repetir: a claquete precisa ficar na tela a janela
> inteira, e vale conferir um quadro do meio do arquivo antes de confiar no número.

### O que decide

Escrever `offset_ms = -220` (os +231 medidos menos o viés de +10,7 do método) no
`lanstream.toml` do Windows e **medir de novo**. Se a mediana cair perto do viés,
a correção vale e o F3.4 fecha; se cair perto de −110, o valor não é constante
entre rodadas e a fase precisa de uma explicação antes de um número.


---

## 12. O atraso acumula por dezenas de minutos, e quem o mede bem é o log do OBS

Duas coisas foram medidas em 31/08 à tarde, e elas só fazem sentido juntas.

### 12.1 O `buffer_ms = 50` estava furando o áudio

Com `buffer_ms = 200` no lugar dos 50, na mesma máquina e no mesmo device:

| | `buffer_ms = 50` | `buffer_ms = 200` |
|---|---|---|
| cobertura | 139/252 (**55%**) | 103/129 (**80%**) |
| estabilidade | blocos de 5 min variando 20 ms | blocos de 2 min dentro de **±3,5 ms** |
| mediana | −260 ms (consenso fraco) | +151,3 ms |

Os 50 ms eram escolha minha, escrita no §2 como "conservador: baixo o suficiente
para não dominar o offset, alto o suficiente para não picotar". A segunda metade
da frase estava errada para este device — o `virtual-audio-capturer` é um filtro
DirectShow sem manutenção desde ~2018, e 50 ms de buffer o fazem perder amostra.
**Perder ~45% das claquetes não é dessincronia, é continuidade**, e foi o aviso
que o script vinha dando desde a primeira gravação do dia.

### 12.2 O que sobra é rampa, e ela leva ~45 minutos para aparecer

O OBS mediu, sozinho e duas vezes, o áudio da fonte atrasado — e agiu:

```
12:34:07  audio is lagging (over by 2490.16 ms) at max audio buffering. Restarting source audio.
14:13:07  audio is lagging (over by 2204.43 ms) at max audio buffering. Restarting source audio.
```

Os dois em conexões com ~45 minutos de vida. Dentro de qualquer janela de 10 ou
20 minutos o valor é plano — foi por isso que as medições de deriva deram sempre
"dentro do ruído". A rampa existe, mas é lenta demais para a janela: o instrumento
adequado para ela é **o log do OBS**, que imprime o acumulado no momento em que
age. Duas linhas de log valem mais que três gravações de 20 minutos aqui.

> **Isto reabilita o diagnóstico que o §10 tinha retirado, mas por outro caminho.**
> Lá eu disse "é deriva" apoiado numa medição de 27% de cobertura e numa linha de
> log de outra sessão. O recuo estava certo: aquela evidência não sustentava a
> conclusão. Agora há duas linhas de log em duas conexões diferentes, ambas com o
> mesmo valor de ordem de grandeza e ambas seguidas de ação do OBS. Mudou a
> evidência, não a vontade de acreditar nela.

### 12.3 A correção: `[audio] resync`

`aresample=async=1:min_hard_comp=0.100:first_pts=0` no áudio de saída, ligado por
default. Ele reamostra para manter o áudio colado na linha de tempo, o que é
exatamente o que uma diferença de relógio pede — e é o que nenhum `offset_ms`
alcança, porque offset é constante e rampa não é.

| Parâmetro | Por quê |
|---|---|
| `async=1` | autoriza esticar/comprimir para fechar o buraco |
| `min_hard_comp=0.100` | acima de 100 ms corta ou insere em vez de esticar — esticar buraco grande vira artefato audível |
| `first_pts=0` | ancora o começo em zero; sem isso um atraso na primeira amostra vira silêncio inicial em vez de correção |

Verificado no ensaio local com o argv real: o ffmpeg aceita `-af` junto com o
`-filter_complex` do vídeo, as duas trilhas saem no TS e a medição continua no
viés (+10,7 ms, 12 de 12). Com o áudio desligado o comando segue **byte a byte** o
da Fase 2.

**O que decide:** uma sessão de 45 min a 1 h com `resync = true`, olhando o log do
OBS. Se as linhas `audio is lagging` não aparecerem, a rampa foi corrigida e o
F3.4 fecha com `offset_ms` cuidando só do que sobrar de constante.
