# Fase 0 — Baseline

Levantamento de hardware, software e rede antes de escrever qualquer código.
Os números aqui viram a referência de regressão para as fases seguintes.

Data: 2026-08-28

---

## 1. Mac (receiver / broadcaster) — ✅ levantado

| Item | Valor |
|---|---|
| Modelo | MacBook Air M4 (`Mac16,12`), 10 cores (4P + 6E) |
| RAM | 16 GB |
| macOS | 26.5.2 (build 25F84), arm64 |
| IP na LAN | `192.168.0.21` (gateway `192.168.0.1`) |
| Interface | **Wi-Fi (`en0`) — não há porta Ethernet** |

### Wi-Fi

| Item | Valor |
|---|---|
| PHY | 802.11ax (Wi-Fi 6) |
| Banda / canal | 5 GHz, canal 104, largura **160 MHz** |
| Sinal / ruído | **-43 dBm** / -93 dBm (SNR 50 dB — excelente) |
| Transmit rate (PHY) | 1814 Mbps, MCS 9 |

> ~~O link é muito melhor do que o plano assumia. A 1.8 Gbps de PHY, um stream de
> 30–50 Mbps ocupa menos de 3% da capacidade. **A recomendação de "use cabo" do
> plano perde força** — e o MacBook Air nem tem porta Ethernet, exigiria adaptador
> USB-C. O que ainda precisa ser medido não é vazão, é **jitter sob carga**
> (ver §4, teste pendente de `iperf3`).~~

> 🔴 **Esta leitura estava errada e o §4 desmentiu.** O PHY de 1814 Mbps não se
> traduziu em vazão utilizável: o `iperf3` mediu **48.7 Mbps de TCP** e perda de
> pacote em UDP já a partir de 17 Mbps. Taxa de PHY do Wi-Fi não é vazão, e aqui a
> distância entre as duas é de mais de 30x. **A recomendação de "use cabo" do plano
> volta a valer com força** — inclusive do lado do Mac, via adaptador USB-C.

### Software instalado nesta fase

| Ferramenta | Versão | Origem |
|---|---|---|
| ffmpeg / ffplay / ffprobe | 8.1 | Homebrew (já estava) |
| OBS Studio | **32.2.2** | `brew install --cask obs` |
| srt (`srt-live-transmit`) | **1.5.7** (lib 1.5.6) | `brew install srt` |
| iperf3 | **3.21** | `brew install iperf3` |
| Python | 3.14.6 + `uv` | já estava |

### ⚠️ Achado: o ffmpeg do Homebrew não tem SRT

A fórmula `ffmpeg` do Homebrew **não linka `libsrt`**. Confirmado por
`ffmpeg -protocols` (só aparece `srtp`, que é Secure RTP — coisa diferente) e por
`brew deps ffmpeg` (11 deps, nenhuma delas srt).

Isso **não bloqueia o projeto**, porque:

- O **OBS traz o próprio `libsrt.dylib`** (verificado em
  `OBS.app/Contents/Frameworks/`) — o Media Source vai falar SRT nativamente, que
  é o caminho de produção.
- Para o preview de diagnóstico, a fórmula `srt` fornece `srt-live-transmit`, que
  faz a ponte SRT → stdout e alimenta o `ffplay`. Sem recompilar nada.

Alternativas descartadas (custo alto, ganho zero): recompilar via
`homebrew-ffmpeg/ffmpeg --with-srt` (build do zero, ~15 min) ou baixar build
estático de terceiro.

**Consequência para a Fase 4:** `lanstream receive --preview` deve ser implementado
como `srt-live-transmit | ffplay`, não como `ffplay srt://...`. E o `doctor` precisa
checar `srt-live-transmit`, não só o protocolo do ffmpeg.

### ✅ Caminho de recepção validado (loopback, sem o Windows)

Teste feito inteiramente no Mac, simulando o sender:

```
ffmpeg (testsrc2 1080p60, h264_videotoolbox, 30M) → udp://127.0.0.1:9999
   → srt-live-transmit → srt://:9000 (listener)
   → srt-live-transmit srt://127.0.0.1:9000 (caller) → ffprobe
```

Resultado: `h264 / 1920x1080 / yuv420p / mpegts`, bitrate medido 55 Mbps.
O receptor, a ponte SRT e o handshake listener↔caller funcionam.
(Script: `scratchpad/selftest.sh`; erro de "decoding MB" no log é só o corte do
`dd` no meio de um frame.)

---

## 2. Windows (sender) — ✅ levantado

Coletado em 2026-08-28 via `scripts/win-doctor.ps1` + inspeção complementar
(`nvidia-smi`, `Get-NetAdapter`, `Win32_SoundDevice`).

| Item | Valor |
|---|---|
| Placa-mãe | Colorful H510M-K M.2 |
| CPU | Intel Core **i3-10105F** @ 3.70 GHz — 4 cores / 8 threads |
| RAM | 15.9 GB |
| GPU | **NVIDIA GeForce RTX 3060, 12 GB** (driver 591.74, VBIOS 94.04.71.40.22) |
| SO | Windows 10 Pro 22H2, build 19045.6466, x64 |
| Monitor | 1 monitor, **1920x1080 @ 60 Hz**, escala DPI **150%** |
| IP na LAN | `192.168.0.12/24` (gateway `192.168.0.1`) |
| Interface | Ethernet Intel I219-V, MAC `EC-D6-8A-BB-3D-83` |
| Link | ⚠️ **100 Mbps full-duplex** (auto-negociação ligada) |
| Disco | `C:` 445 GB (**61.8 GB livres**), `E:` 930 GB (231.8 GB livres) |

### Software — toolchain completo

| Ferramenta | Versão | Origem |
|---|---|---|
| ffmpeg / ffplay / ffprobe | **8.1 full_build** | `winget install --id Gyan.FFmpeg -e --version 8.1` |
| iperf3 | **3.21** | `winget install --id ar51an.iPerf3 -e` |
| Python | **3.13.15** | `winget install --id Python.Python.3.13 -e` |
| uv | **0.12.7** | `winget install --id astral-sh.uv -e` |
| OBS Studio | — | não é necessário deste lado |

Paridade com o Mac em duas ferramentas que importam: **ffmpeg 8.1** e **iperf3
3.21**, as mesmas versões das duas pontas. O Python do Mac é 3.14.6 contra 3.13.15
aqui — sem problema, o plano pede 3.11+.

**Não use ffmpeg 9.0.1** — ver o achado do NVENC abaixo.

> Antes disso a máquina tinha apenas o stub do Python da Microsoft Store, que não
> é um interpretador real.

### ✅ Ambiente da Fase 1 validado

`uv venv --python 3.13` + `uv pip install typer psutil tomli-w` resolve e importa
sem erro: `typer 0.27.2`, `psutil 7.2.2`, `tomli_w 1.2.0`, `tomllib` da stdlib.
As dependências do §3.4 do plano estão todas disponíveis — a Fase 1 pode começar.

### ✅ Capacidades do ffmpeg verificadas

| Item | Resultado |
|---|---|
| `ddagrab` | ✅ presente **e capturando** — testado contra a tela real, não só listado em `-filters` |
| Protocolo SRT | ✅ `srt OK` |
| `h264_nvenc` | ✅ funciona (teste de encode real, não só listagem) |
| `hevc_nvenc` | ✅ funciona |
| `av1_nvenc` | ❌ `No capable devices found` — esperado: Ampere decodifica AV1 mas não encoda (só Ada / RTX 40+) |
| `h264_qsv`, `*_amf` | ❌ ruído da build — o i3-10105**F** não tem iGPU e não há GPU AMD. **Só o NVENC importa nesta máquina.** |
| Devices dshow | ❌ **nenhum** — `Could not enumerate video devices`, `Could not enumerate audio only devices` |

### ✅ Pipeline de produção validado ponta a ponta (local)

```
ffmpeg -f lavfi -i ddagrab=output_idx=0:framerate=60 \
       -c:v h264_nvenc -preset p4 -tune ll -b:v 30M -f mpegts saida.ts
```

Resultado: **exit 0**, `h264 / 1920x1080 / yuv420p / 60 fps / mpegts`, 5.0 s de
duração, rodando a **59 fps com speed 0.99x** — ou seja, tempo real folgado.
Captura e encode acontecem inteiros na GPU.

**Isso derruba o maior risco do projeto.** O `ddagrab` captura o desktop e o NVENC
encoda em tempo real. O que ainda não foi provado é o `ddagrab` capturando **o jogo
em fullscreen exclusivo**, que é um caso diferente do desktop — continua sendo o
alvo do Teste 1.

### ✅ SRT validado ponta a ponta (tudo menos o Mac)

O caminho inteiro do Teste 1 foi exercitado localmente: sender em `listener` na
porta 9000 e um segundo ffmpeg em `caller` no lugar do Mac.

| Teste | Resultado |
|---|---|
| Handshake SRT via `127.0.0.1` | ✅ caller identificou `h264 / 1920x1080 / 60 fps / mpegts` |
| Handshake SRT via **IP da LAN** (`192.168.0.12`) | ✅ 12.0 s recebidos, 45 MB, **30.1 Mbps** |
| `h264_nvenc` CBR 30M, fonte em movimento | ✅ **30.59 Mbps** sustentados, `Main profile` |
| `hevc_nvenc` sobre SRT | ✅ funciona, `Main profile` — é o codec-alvo do §3.3 |
| `latency=120000` (120 ms) no SRT | ✅ sem erro nos dois lados |

**Bitrate de referência com a tela em movimento: ~29.6–30.6 Mbps** com `-rc cbr
-b:v 30M`. O rate control cumpre o alvo com precisão. Num link de 100 Mbps isso é
~30% do canal.

> O número de 1.6 Mbps que aparece em testes com o desktop parado **não é
> referência** — sem movimento o NVENC quase não gera bits.

### ⚠️ Achado: o `ddagrab` limita em ~56–58 fps, não 60

Com a tela em movimento, o pipeline entrega **55–58 fps** de forma consistente, e
`speed` fica entre 0.95x e 0.99x. O déficit é de ~3–5%.

**O gargalo não é o encoder.** Com fonte sintética (sem `ddagrab`), o mesmo
`h264_nvenc -preset p5 -tune hq` roda a **270 fps / speed 4.47x** — quase 5x tempo
real. Quem limita é a captura.

Varredura de presets, todos com a tela em movimento:

| Preset / tune | fps | speed | drop |
|---|---|---|---|
| `p1` / `ll` | 58 | 0.981x | 0 |
| `p4` / `ll` | 58 | 0.980x | 0 |
| `p5` / `hq` (o do script) | 57 | 0.978x | 0 |
| `p7` / `hq` | 55 | 0.953x | 0 |

Ou seja: dá para usar preset alto quase de graça — do `p1` ao `p5` são 1 fps de
diferença. Só o `p7` cobra caro (3 fps) sem ganho proporcional. Isso reforça a
decisão do §3.1 do plano (qualidade > latência) e é insumo direto pra Fase 7.

**Ainda em aberto:** medir isso com jogo real. Um jogo em fullscreen exclusivo
muda como a Desktop Duplication API entrega frames, e o número pode tanto melhorar
(frames de verdade em vez de tela parada) quanto piorar.

### 🐛 Bug corrigido em `scripts/win-test-video.ps1`

O script não rodava. O ramo `nvidia` montava:

```
ddagrab=0:framerate=60,hwmap=derive_device=cuda,scale_cuda=format=nv12
```

e o ffmpeg abortava antes do primeiro frame:

```
[Parsed_hwmap_1] Failed to created derived device context: -40.
[fc#0] Error configuring filter graph: Function not implemented
```

O `-40` é `ENOSYS`: **este build não consegue derivar um device CUDA a partir do
D3D11**. Testei as alternativas:

| Cadeia | Resultado |
|---|---|
| `ddagrab` direto pro `h264_nvenc` | ✅ 58 fps, 0.98x |
| `ddagrab,hwdownload,format=bgra,format=nv12` (CPU) | ✅ 58 fps, 0.97x |
| `ddagrab,hwmap=derive_device=cuda,scale_cuda=...` | ❌ `derived device context: -40` |
| `ddagrab,scale_d3d11=format=nv12` | ❌ `Failed to configure output pad` |

**Correção aplicada:** passar o `ddagrab` direto pro `h264_nvenc`, sem filtro de
conversão. O ffmpeg resolve o formato sozinho e o desempenho é o mesmo. O preset
`p5`/`hq` foi mantido de propósito — a varredura acima mostra que ele custa 1 fps
contra o `p4`/`ll`, e o §3.1 do plano prioriza qualidade.

Depois da correção o script roda ponta a ponta e o caller recebe pela LAN
normalmente (30.1 Mbps, 12 s, sem erro).

> Os ramos `amd`, `intel` e `cpu` do script **não foram testados** — esta máquina
> não tem GPU AMD nem iGPU Intel. Só o `nvidia` está verificado.

### ⚠️ Achado: ffmpeg 9.0.1 quebra o NVENC com o driver atual

A primeira instalação trouxe a **9.0.1**, e os três encoders NVIDIA falharam:

```
Driver does not support the required nvenc API version. Required: 13.1 Found: 13.0
The minimum required Nvidia driver for nvenc is 610.00 or newer
```

A 9.0.1 foi compilada contra headers de NVENC que exigem driver **≥ 610.00**; o
driver instalado é o **591.74** (API 13.0). Não é limitação da GPU — é o par
ffmpeg/driver fora de sincronia.

**Resolvido baixando para a 8.1**, que casa com o driver atual e ainda iguala a
versão do Mac. A alternativa (atualizar o driver para ≥610.00 e manter a 9.0.1)
foi descartada por criar divergência de versão entre as duas máquinas sem ganho.

⚠️ **Consequência operacional:** não deixar o `winget upgrade` subir o ffmpeg sem
antes conferir o driver, ou o NVENC quebra de novo silenciosamente.

### ⚠️ Achado crítico: o link Ethernet negocia a 100 Mbps, não 1 Gbps

O Intel I219-V é **gigabit**, e a auto-negociação está ativa — ainda assim o link
subiu a **100 Mbps**. Isso não é configuração, é limitação física do caminho:
cabo Cat5 (ou Cat5e danificado / com par rompido), porta 100M no roteador, ou um
switch antigo no meio.

**Consequência direta no plano:** a meta do §4 — *"≥ 100 Mbps sustentados no TCP"* —
é **inalcançável** neste link. O teto teórico é 100 Mbps e o real de TCP fica em
~94 Mbps. O stream de 30–50 Mbps previsto ocupa **30–50% do canal**, contra os
<3% que o lado do Mac sugeria. Não inviabiliza, mas some a margem: qualquer outro
tráfego na rede (backup, update do Windows, outro dispositivo) passa a competir.

A ironia é que o gargalo inverteu — o plano recomendava cabo por desconfiar do
Wi-Fi, mas aqui o **Wi-Fi 6 do Mac (1814 Mbps PHY) é ~18x mais rápido que o cabo
do Windows**.

**Ação sugerida antes do Teste 2:** trocar o cabo por um Cat5e/Cat6 conhecido e
conferir a porta do roteador. Se subir para 1 Gbps, o `LinkSpeed` muda sozinho.
Se não subir, revisar as metas do §4 para o que 100 Mbps comporta.

### ⚠️ Áudio: não existe device de loopback

`Win32_SoundDevice` lista apenas:

- Realtek High Definition Audio (onboard)
- NVIDIA High Definition Audio (saída HDMI/DP)
- NVIDIA Virtual Audio Device (WDM) — **não serve**: é o caminho de áudio do
  driver NVIDIA para HDMI/DP, não um loopback de captura.

Ou seja: **nenhum VB-CABLE / virtual-audio-capturer**. A Fase 3 (áudio) começa do
zero. Confirma o risco que estava aberto no §7.

### ✅ Firewall — regra criada

```powershell
New-NetFirewallRule -DisplayName "lanstream SRT" -Direction Inbound `
  -Protocol UDP -LocalPort 9000 -Action Allow -Profile Private
```

Criada e confirmada: `Enabled=True`, `Inbound`, `Allow`, `UDP/9000`, perfil
`Private`. O perfil da conexão Ethernet **é** `Private`, então a regra vale de
fato — se a rede for reclassificada como `Public` em algum momento, a regra para
de valer e o Mac deixa de conectar.

### ✅ Rede até o Mac

`ping 192.168.0.21`: 4/4 respostas, **3 ms** estáveis (a primeira, 105 ms, é só
resolução ARP). Porta 9000/UDP livre, sem nada escutando.

### Próximos passos deste lado

Tudo que dependia só desta máquina está feito:

1. ~~Instalar o ffmpeg~~ ✅ 8.1 full.
2. ~~Rodar o `win-doctor` para fechar as checagens pendentes~~ ✅.
3. ~~Instalar o iperf3~~ ✅ 3.21.
4. ~~Criar a regra de firewall~~ ✅ UDP 9000, perfil Private.
5. ~~Instalar Python e uv~~ ✅ 3.13.15 e 0.12.7, com deps da Fase 1 validadas.

O que sobrou **precisa de você ou da outra máquina**:

6. Investigar o link de 100 Mbps — trocar o cabo por Cat5e/Cat6 e conferir a porta
   do roteador. Não dá para diagnosticar por software.
7. Rodar o Teste 1 com o Mac ligado (§3) e o Teste 2 com o `iperf3 -s` lá (§4).
8. Rodar o Teste 1 **com um jogo real em fullscreen exclusivo** — é o único risco
   grande que continua sem resposta.
9. Fase 3: instalar um loopback de áudio (VB-CABLE). Exige driver e reboot, então
   ficou de fora deste levantamento.

---

## 3. Teste 1 — vídeo ponta a ponta ✅ executado

Rodado com o Mac de verdade do outro lado, via
`scripts/win-test-video.ps1 -Gpu nvidia -Bitrate <X>` no Windows e
`./scripts/mac-preview.sh 192.168.0.12` no Mac.

| | **30M** (padrão do script) | **15M** |
|---|---|---|
| Duração até cair | **13.55 s** | **26.95 s** |
| Frames | 777 | 1586 |
| fps | 56 | **58** |
| Bitrate medido | 29.3 Mbps | **15.07 Mbps** (travado) |
| speed | 0.983x | **0.993x** |
| Frames perdidos na captura | 5 | — |
| Fim | `Error submitting a packet to the muxer: I/O error` | idem |

**O vídeo chega no Mac.** O caminho completo — `ddagrab` → `h264_nvenc` → MPEG-TS →
SRT listener → LAN → Mac — funciona de ponta a ponta. Isso fecha o critério
principal do Teste 1.

A 15M o stream fica visivelmente mais saudável: bitrate cravado em 15.07 Mbps,
`speed` em 0.993x e **58 fps** contra os 56 da corrida a 30M.

### ⚠️ Ressalva honesta sobre a causa da queda

As duas corridas terminaram em `I/O error`, e **não dá para afirmar daqui por que
elas terminaram**. O `I/O error` no lado do sender é o que aparece tanto quando o
SRT colapsa por congestionamento quanto quando o `ffplay` é simplesmente fechado
no Mac. Não houve instrumentação para distinguir os dois casos.

O que os números sugerem, sem provar: a corrida a 30M durou metade da corrida a
15M, e 30 Mbps está muito acima do teto limpo de 16 Mbps medido no §4. É
consistente com congestionamento, mas é correlação, não causa estabelecida.

**Como fechar isso de verdade:** rodar as duas de novo cronometrando o fechamento
do `ffplay`, ou deixar o `mac-preview.sh` rodando 10 minutos sem tocar. Se a 15M
sobreviver 10 min e a 30M cair sempre por volta dos 13 s, aí sim é congestionamento.

## 4. Teste 2 — vazão e jitter ✅ executado

`iperf3 3.21` nos dois lados, Mac como servidor (`iperf3 -s`).

### TCP — 30 s

```
iperf3 -c 192.168.0.21 -t 30
```

| Métrica | Valor | Alvo |
|---|---|---|
| Média | **48.7 Mbps** | ≥100 Mbps ❌ |
| Faixa por segundo | 27 – 62 Mbps | — |
| Transferido | 174 MB | — |

Não só ficou muito abaixo do alvo como **oscilou o tempo todo**, quase 2:1 entre o
pior e o melhor segundo.

### UDP — o que importa pra SRT

```
iperf3 -c 192.168.0.21 -u -b <X> -t 30
```

| Alvo | Recebido | Jitter | **Perda** |
|---|---|---|---|
| 5 Mbps | 4.99 Mbps | 0.582 ms | **0%** |
| 10 Mbps | 9.98 Mbps | 0.123 ms | **0%** |
| 15 Mbps | 15.0 Mbps | 0.167 ms | **0%** |
| **16 Mbps** | 16.0 Mbps | 0.010 ms | **0%** ← teto limpo |
| 17 Mbps | 16.9 Mbps | 0.227 ms | 0.21% |
| 18 Mbps | 17.9 Mbps | 0.046 ms | 0.53% |
| 20 Mbps | 19.6 Mbps | 0.187 ms | 1.6% |
| 25 Mbps | 23.9 Mbps | 0.085 ms | **4.4%** |

**O jitter passa folgado em toda a faixa** — sempre abaixo de 0.6 ms contra um alvo
de 5 ms. O problema é inteiramente **perda de pacote**, e ela tem um joelho
nítido: some completamente até 16 Mbps e cresce rápido depois.

### 🔴 O que isso significa pro projeto

> ⚠️ **Leia o §4c antes de agir por esta seção.** As conclusões abaixo foram
> escritas com o EEE da placa ainda ligado e sem testar o sentido inverso.
> Depois disso o TCP subiu para 68 Mbps e ficou provado que o caminho é
> assimétrico — o "teto de 16 Mbps" é artefato da rajada não pacejada do
> `iperf3 -u`, não um limite real para a SRT.

**O teto utilizável é 16 Mbps.** O §3.3 do plano tinha acabado de ser revisto para
20–25 Mbps HEVC — e mesmo esse alvo, já bem mais modesto que os 30–60 originais,
**não cabe**: a 20 Mbps a rede perde 1.6% e a 25 Mbps perde 4.4%.

> O raciocínio que levou aos 20–25 Mbps continua correto e é o que salva a
> situação: como o OBS reencoda pra Twitch a 6–8 Mbps, o stream da LAN só precisa
> ser transparente o bastante pra não empilhar artefato. Se 20 Mbps já era ~3x o
> que a Twitch mostra, **15 Mbps ainda é ~2x**. O corte é de transporte, não de
> qualidade percebida.

> Os comandos rodados foram `iperf3 -c 192.168.0.21 -t 30` e
> `iperf3 -c 192.168.0.21 -u -b 25M -t 30`, mais uma varredura de 5M a 25M para
> achar o joelho. O teste de estresse a 60 Mbps foi dispensado: a 25 Mbps a perda
> já era 44x o alvo, então forçar mais não acrescentaria informação.

Duas anomalias que valem registro:

1. **UDP degrada muito antes do TCP.** O TCP sustenta 48.7 Mbps de média, mas o UDP
   já perde pacote a 17 Mbps. O normal seria o oposto — UDP não tem controle de
   congestionamento e costuma alcançar mais. Essa inversão aponta para **fila /
   buffer no caminho** (provavelmente o AP), não para falta de banda bruta.
2. **48.7 Mbps é metade do que um link de 100 Mbps deveria dar.** Então o cabo de
   100 Mbps do §2 não explica tudo sozinho. O Mac está em **Wi-Fi**, e a oscilação
   de 27–62 Mbps tem assinatura de meio sem fio.

**Consequências práticas:**

- O alvo de "≥100 Mbps TCP" do plano não é só inalcançável no link atual — está a
  2x de distância do que a rede entrega hoje.
- **HEVC deixa de ser preferência e vira necessidade.** O §3.3 já elegia
  `hevc_nvenc` como alvo; a 15 Mbps HEVC entrega aproximadamente a qualidade de
  ~25 Mbps em H.264. É o que torna 1080p60 viável dentro do teto medido.
- A SRT tem ARQ e **recupera parte da perda** retransmitindo. A 17–20 Mbps
  (0.2–1.6%) provavelmente ainda dá, com folga de latência maior. A 25 Mbps (4.4%)
  é pedir demais.
- Antes de aceitar 16 Mbps como limite do projeto, vale atacar a rede: trocar o
  cabo do Windows por Cat5e/Cat6 e, principalmente, **testar com o Mac no cabo**
  (exige adaptador USB-C, já que o MacBook Air não tem porta Ethernet) para isolar
  quanto da perda é do Wi-Fi.

### Sobre o ping no sentido inverso (Mac → Windows)

`ping 192.168.0.12` a partir do Mac dá **100% de perda** — mas isso **não é
problema de rede**. O Firewall do Windows dropa ICMP echo de entrada por padrão.
A prova de que o caminho está bom: o ARP do Mac resolve o IP para
`ec:d6:8a:bb:3d:83`, exatamente o MAC do I219-V registrado em §2. O host responde
em camada 2, está online e alcançável.

Isso não afeta o projeto: o Mac é o **caller** do SRT e conecta na UDP 9000 do
Windows, que tem regra de allow explícita. Só significa que **`ping` não serve
como teste de saúde** nesse sentido — use `iperf3` ou o próprio handshake SRT.

## 4b. 🔴 Teste 1 parcial — SRT conecta, mas o stream chega quebrado

Primeira execução conjunta (sender `win-test-video.ps1` no Windows, receptor
headless no Mac). O handshake funciona pela LAN, mas o vídeo chega degradado.

### O que foi medido

| Item | Resultado |
|---|---|
| Handshake SRT pela LAN | ✅ `SRT source connected` |
| Stream identificado | ✅ `h264 (Main) / 1920x1080 / yuv420p / 60 fps / mpegts` |
| Frames recebidos | 🔴 **527 frames em 18.2 s de stream ≈ 29 fps** (metade dos 60) |
| Integridade | 🔴 dezenas de `error while decoding MB` e `concealing N DC/AC/MV errors`, inclusive **em I-frames** |

### Causa raiz: pacotes chegando ~900 ms atrasados

O log do `srt-live-transmit` é inequívoco:

```
RCV-DROPPED 38 packet(s). Packet seqno %1646696756 delayed for 838.442 ms
RCV-DROPPED 23 packet(s). ...                       delayed for 888.708 ms
RCV-DROPPED 22 packet(s). ...                       delayed for 975.032 ms
RCV-DROPPED 44 packet(s). ...                       delayed for 964.900 ms
RCV-DROPPED 64 packet(s). ...                       delayed for 885.049 ms
```

O buffer do SRT está em **120 ms**. Tudo que chega depois disso é descartado por
definição — não é perda de pacote, é **pacote velho demais para ser útil**.

O atraso é **estável em torno de 850–975 ms**, não crescente e não errático. Essa
assinatura é de **fila permanentemente cheia** em algum ponto do caminho
(bufferbloat), não de jitter aleatório.

### Três hipóteses, ainda não separadas

1. **Oversubscription do caminho** — o sender oferece mais do que o caminho
   entrega, e forma-se fila. Candidato principal. O link Ethernet do Windows é de
   100 Mbps (§2) e o teste rodou com o default de **30 Mbps**.
2. **Buffer do SRT pequeno demais para este caminho** — se o atraso for fila
   *limitada*, subir a latência do SRT resolve sozinho. E, pelo §3.1 do PLANO,
   **latência é barata aqui**: 1 s de buffer não custa nada, porque o jogo é
   jogado no Windows.
3. **Contrapressão do meu lado** — `srt-live-transmit → pipe → ffmpeg` com decode
   por software poderia parar de drenar o socket. **Não descartada**: a bissecção
   estava rodando quando o sender caiu.

### Experimento que separa as três (fazer nesta ordem)

**Primeiro, `iperf3`** — nunca foi rodado, e é exatamente o que responde a (1):

```powershell
iperf3 -c 192.168.0.21 -t 30            # TCP: teto real do caminho
iperf3 -c 192.168.0.21 -u -b 25M -t 30  # UDP no bitrate-alvo: jitter e perda
```

**Depois, o sender com buffer grande e bitrate menor** — testa (2) e (1) juntos:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\win-test-video.ps1 -Gpu nvidia -Bitrate 20M
```

com o SRT em **1 s** de latência dos dois lados (`latency=1000000` no ffmpeg do
Windows, `latency=1000` no `srt-live-transmit` do Mac — o ffmpeg conta em
**microssegundos** e o srt-live-transmit em **milissegundos**, pegadinha fácil).

- Se limpar → era (2), e a correção é gratuita: buffer maior no `lanstream`.
- Se continuar sujo a 20 Mbps → era (1), e aí **a troca do cabo deixa de ser
  opcional**.

### ⚠️ Isso pode reverter a reclassificação do link de 100 Mbps

O PLANO §5 rebaixou o link de 100 Mbps para risco 🟢 baixo, com o argumento de que
20–25 Mbps ocupam só ~25% do canal. **Este resultado é a primeira evidência
contrária.** A reclassificação fica pendente do `iperf3`: se o caminho não
entregar ~90 Mbps limpos, o argumento cai e o cabo vira pré-requisito.

---

## 4c. ✅ Respondendo o §4b — o caminho é assimétrico

O §4b levantou três hipóteses e pediu o `iperf3` para separá-las. Rodado. Também
foram testadas duas hipóteses de causa que apareceram no caminho.

### ❌ Hipótese descartada: uTorrent consumindo o upload

Havia um uTorrent enviando a ~5 MB/s (**40 Mbps**) durante a primeira medição.
Somados aos 48.7 Mbps medidos, dá ~89 Mbps — suspeitosamente perto do teto de um
link de 100 Mbps, então a explicação parecia perfeita.

**Não era.** Com o uTorrent fechado, o perfil de perda ficou igual: 20 Mbps passou
de 1.6% para 1.5%, 25 Mbps de 4.4% para 4.7%. Dentro do ruído. O TCP até caiu
(37.4 Mbps numa corrida). Hipótese testada e rejeitada — vale registrar para
ninguém reinvestigar.

### ✅ Causa parcial encontrada: Energy Efficient Ethernet

A placa do Windows estava com **EEE ligado** (`EEELinkAdvertisement`). Desligado
com:

```powershell
Set-NetAdapterAdvancedProperty -Name Ethernet `
  -DisplayName "Ethernet com uso eficiente de energia" -DisplayValue "Desligado"
Restart-NetAdapter -Name Ethernet
```

| TCP Windows→Mac | Antes (EEE on) | Depois (EEE off) |
|---|---|---|
| 3 corridas de 15 s | 46.1 / 56.6 / 42.4 Mbps | **66.0 / 68.9 / 68.2 Mbps** |

**Ganho de ~40% e, mais importante, a variância sumiu** — as amostras não se
sobrepõem. Ficou permanente na placa.

> O link **continuou negociando 100 Mbps** depois do EEE off, então o EEE não era a
> causa da negociação em 100M. São dois problemas diferentes.

### 🔴 O achado principal: o caminho é fortemente assimétrico

| Direção | TCP | UDP 25M | UDP 60M |
|---|---|---|---|
| **Windows → Mac** (o do stream) | 68 Mbps | 5.5% perda | — |
| **Mac → Windows** | **93.5 Mbps** | **0% perda** | **0% perda** |

O sentido Mac→Windows satura o link de 100 Mbps e entrega **60 Mbps de UDP sem
perder um pacote**. O sentido do stream, não.

**Isso inocenta boa parte do que estava sob suspeita.** O cabo do Windows carrega
93.5 Mbps de entrada; a placa não acusa nenhum `OutboundPacketError` nem
`OutboundDiscardedPacket`. O Wi-Fi do Mac transmite 60 Mbps limpos. O que sobra é
a perna **roteador → Mac** (downlink do AP), que é justamente a única que os dois
testes não compartilham.

### Pista adicional: pacote menor, mais perda

No mesmo bitrate, reduzir o payload piora:

| Payload | 20 Mbps | 25 Mbps |
|---|---|---|
| ~1450 B (padrão) | 3.3% | 5.5% |
| 1400 B | 4.2% | 6.0% |
| 1200 B | **7.8%** | **7.8%** |

Mesma banda, mais pacotes, mais perda. A assinatura é de **limite de taxa de
pacotes / contenção de airtime**, não de falta de largura de banda.

### ⚠️ O "teto de 16 Mbps" do §4 era pessimista demais

O §4 concluiu que o teto utilizável eram 16 Mbps. **Isso superestima o problema**,
por um motivo metodológico: o `iperf3` em UDP dispara rajadas não pacejadas na taxa
alvo. O TCP, que se auto-pacea, alcança 68 Mbps no mesmo caminho — 4x o suposto
teto. Um transporte que espaça os pacotes vê um caminho muito melhor do que o
`iperf3 -u` sugere.

**A SRT se pacea e tem ARQ**, e foi desenhada exatamente para links com alguns por
cento de perda. Então os números de perda acima **não se traduzem direto** em
qualidade de stream. O que decide não é o `iperf3` — são as estatísticas da própria
SRT em stream real.

### Como isso responde às três hipóteses do §4b

| Hipótese do §4b | Veredito |
|---|---|
| **(1) Oversubscription do caminho** | 🟡 **Parcial.** A 30 Mbps o sender pede mais do que o downlink entrega com folga, então há fila. Mas o caminho não é tão estreito quanto parecia: 68 Mbps de TCP. |
| **(2) Buffer do SRT pequeno demais** | 🟢 **Principal suspeita agora.** O §4b mediu atraso **estável em 850–975 ms** — fila profunda mas *limitada*, não crescente. Com buffer de 120 ms, tudo isso vira `RCV-DROPPED` por definição. Subir para 1.2 s deve limpar, e pelo §3.1 do PLANO isso é de graça. |
| **(3) Contrapressão no Mac** | ⚪ **Continua aberta** — nada medido daqui responde. |

### Próximo experimento (é o que decide)

Exatamente o que o §4b propôs, agora com o `iperf3` já feito:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\win-test-video.ps1 -Gpu nvidia -Bitrate 20M
```

com **latência SRT de 1.2 s dos dois lados** — `latency=1200000` no ffmpeg
(microssegundos) e `latency=1200` no `srt-live-transmit` (milissegundos).

- Se limpar → era (2). Correção gratuita: buffer maior no `lanstream`, e o alvo de
  bitrate pode voltar a subir.
- Se continuar sujo → o gargalo é mesmo o downlink do AP, e aí o caminho é **pôr o
  Mac no cabo** (adaptador USB-C), não trocar o cabo do Windows — que já provou
  carregar 93.5 Mbps.

---

## 4d. ✅ Experimento do buffer de 1.2 s — fechado

O experimento que o §4b propôs e o §4c refinou: **20 Mbps com buffer SRT de 1.2 s**
nos dois lados, para separar "fila limitada, buffer pequeno" de "caminho estreito
demais".

```powershell
powershell -ExecutionPolicy Bypass -File scripts\win-test-video.ps1 `
  -Gpu nvidia -Bitrate 20M -LatencyMs 1200
```

```bash
./scripts/mac-preview.sh 192.168.0.12 9000 1200
```

> Os dois scripts ganharam parâmetro de latência para este teste — antes o valor
> era fixo em 120 ms nos dois. **Cuidado com a unidade:** o ffmpeg conta em
> microssegundos e o `srt-live-transmit` em milissegundos. Ambos os scripts agora
> recebem **milissegundos** e convertem internamente.

### O que o lado do sender mostrou

| Corrida | Duração | fps | speed | Bitrate |
|---|---|---|---|---|
| 30M / buffer 120 ms | 13.55 s | 56 | 0.983x | 29.3 Mbps |
| 15M / buffer 120 ms | 26.95 s | 58 | 0.993x | 15.07 Mbps |
| **20M / buffer 1200 ms** | **31.93 s** | 🔴 **48** | 🔴 **0.942x** | 17.35 Mbps |

**O sender foi freado.** Nas corridas anteriores ele mantinha 56–58 fps e speed
~0.99x; com o buffer grande caiu para 48 fps e 0.942x. A queda de bitrate para
17.35 Mbps é consequência disso, não causa: 48/60 × 20 ≈ 16, bate.

Isso é **contrapressão**. Com buffer de 120 ms a SRT descartava o que atrasava
(daí os `RCV-DROPPED` do §4b) e o sender seguia livre. Com 1.2 s ela **segura** em
vez de descartar, o buffer de envio enche, a escrita bloqueia e o freio chega até
a captura.

### O que isso sugere — e o que ainda não prova

A contrapressão é evidência de que o caminho **realmente não absorve 20 Mbps** no
sentido Windows→Mac. Reforça a hipótese (1) do §4b (oversubscription) e enfraquece
a ideia de que era só buffer pequeno: aumentar o buffer não fez o caminho ficar
mais largo, só trocou *descarte* por *espera*.

> ⚠️ **Mas a metade que decide não foi medida.** Todo o critério do experimento
> está no receptor: sumiram os `RCV-DROPPED`? sumiu o `error while decoding MB`?
> o fps de chegada subiu dos ~29 do §4b? Nada disso dá pra ver do lado do Windows.
>
> **48 fps chegando limpo seria um resultado bom**, melhor que 29 fps corrompidos.
> **48 fps chegando corrompido seria um resultado ruim.** Os dois produzem
> exatamente o mesmo log no sender.

Segunda ressalva: não há confirmação de que o receptor rodou com **1200 ms**. Se o
Mac usou a versão antiga do `mac-preview.sh` (latência fixa em 120 ms), o teste não
é o que se pretendia. A SRT negocia a latência efetiva como o **maior** valor entre
os dois lados, então provavelmente valeu 1200 mesmo assim — mas isso é inferência,
não observação.

### Para fechar

Rodar de novo com `git pull` feito nos dois lados e **guardar o log do
`srt-live-transmit`**, que é onde estão os `RCV-DROPPED ... delayed for`. Com esse
log, o experimento se resolve em um minuto.

Se confirmar que 20 Mbps não passa mesmo com buffer grande, o caminho seguinte não
é mexer em bitrate nem em buffer: é **pôr o Mac no cabo** (adaptador USB-C) e
eliminar o downlink do AP, que o §4c isolou como a única perna suspeita.

### ✅ A metade que faltava — medida do lado do Mac

O receptor rodou contra **esta mesma corrida** (20M / buffer 1200 ms), com
`srt-live-transmit ... latency=1200` e o log guardado.

| Critério do experimento | Resultado |
|---|---|
| `RCV-DROPPED` | ✅ **0** (eram dezenas por corrida a 120 ms) |
| `error while decoding` / `concealing` | ✅ **0** (eram dezenas, inclusive em I-frames) |
| Frames recebidos | **1294 em 25.00 s ≈ 52 fps** |
| fps de processamento / speed | 57 / 1.09x |

**48 fps chegando limpo** — que é, pelo critério escrito acima, o resultado bom.
Os ~52 fps medidos na chegada batem com os 48 fps relatados pelo sender (janelas
de medição diferentes). E a dúvida sobre a latência efetiva fica resolvida por
observação, não por inferência: o receptor rodou com 1200 ms explícitos.

---

## 4e. 🔎 Síntese: era a rede **e** o buffer, com papéis diferentes

Juntando as duas metades, e **corrigindo duas leituras minhas que estavam erradas**:

> ❌ Eu tinha atribuído tudo ao uTorrent. O §4c rejeitou isso com teste controlado.
> ❌ Depois concluí "era o buffer, não a rede". Também está errado — a
> contrapressão medida no sender mostra que o caminho é, sim, o limite.

O quadro que explica **todas** as observações de uma vez:

1. **O caminho Windows→Mac entrega ~17 Mbps limpos.** O sender foi freado até
   17.35 Mbps e nessa taxa a entrega foi perfeita. Isso é notavelmente próximo do
   joelho de ~16 Mbps que o `iperf3 -u` do §4 encontrou — os dois métodos, por
   caminhos independentes, apontam o mesmo teto.
2. **O buffer do SRT não muda a capacidade — muda o modo de falhar.**
   - Buffer pequeno (120 ms): a SRT **descarta** o que atrasa. O sender corre solto
     a 30 Mbps, o excesso vira `RCV-DROPPED`, e o que chega vem **corrompido**.
   - Buffer grande (1.2 s): a SRT **segura** em vez de descartar. A contrapressão
     sobe até a captura, o sender cai para 48 fps — e o que chega vem **perfeito**.

   Ou seja: o buffer grande trocou **corrupção** por **degradação graciosa de
   framerate**. Para este projeto isso é claramente melhor, mas não é o mesmo que
   resolver.
3. **A hipótese (3) do §4b (contrapressão *no Mac*) continua descartada.** A
   contrapressão medida é do SRT freando o sender, não do receptor deixando de
   drenar: o caminho `srt-live-transmit → pipe → ffmpeg` foi idêntico nas corridas
   suja e limpa.

### O que fica decidido

- **Buffer alto vira default do `lanstream`** (1.2 s nas duas pontas). Pelo §3.1 do
  PLANO é de graça, e a diferença entre corrompido e limpo é grande demais para
  tratar como tuning.
- **O teto de ~16–17 Mbps do §4 se sustenta** e não era artefato de rajada do
  `iperf3` — foi confirmado por um transporte pacejado, com ARQ, em stream real.
- **HEVC volta a ser requisito, não preferência**, como o §4 já dizia: dentro de
  ~16 Mbps é o que torna 1080p60 viável.
- **Falta um teste para fechar:** `hevc_nvenc -Bitrate 15M -LatencyMs 1200`. Se o
  sender mantiver 57–58 fps e o receptor continuar em 0 drops, o projeto tem uma
  configuração de produção e a rede sai do caminho crítico. **É o próximo passo.**
- Se ainda houver freio a 15 Mbps, aí sim o caminho é **pôr o Mac no cabo**
  (adaptador USB-C), que o §4c isolou como a única perna suspeita.

---


---

## 5. Teste 3 — dentro do OBS ⏳ pendente

Media Source apontando para
`srt://<IP-WINDOWS>:9000?mode=caller&latency=120000`, `Input Format = mpegts`.
Rodar 10 minutos e conferir estabilidade.

## 6. Latência ponta a ponta ⏳ pendente

Abrir um cronômetro com centésimos em tela cheia no Windows e fotografar as duas
telas juntas. Anotar o valor — **é referência, não meta**: o jogo é jogado no
Windows, então latência alta só afeta o sync com o microfone (§3.1 do PLANO).

---

## 7. Riscos revisados após o levantamento

| Risco | Status |
|---|---|
| **Contrapressão do SRT freando o sender** | 🟡 **Novo (§4d).** Com buffer de 1.2 s a 20 Mbps o sender caiu de 56–58 fps para **48 fps** e speed 0.942x. Buffer maior trocou descarte por espera, não alargou o caminho. Falta o log do receptor para saber se a imagem chegou limpa. |
| **A rede não sustentar o bitrate** | 🟡 **Menos grave do que o §4 concluiu, ver §4c.** Com o EEE desligado o TCP faz **68 Mbps** no sentido do stream. O "teto de 16 Mbps" era artefato da rajada do `iperf3 -u`; a SRT se pacea e tem ARQ. Pendente do experimento de buffer de 1.2 s. |
| **Caminho assimétrico (downlink do AP)** | 🔴 **Novo, e é o gargalo real.** Mac→Windows faz 93.5 Mbps de TCP e 60 Mbps de UDP com 0% de perda; Windows→Mac faz 68 Mbps de TCP e perde 5.5% de UDP a 25 Mbps. A única perna não compartilhada é **roteador → Mac**. Payload menor piora a perda, o que aponta para contenção de airtime. |
| **EEE ligado na placa do Windows** | 🟢 **Resolvido.** `EEELinkAdvertisement` desligado: TCP passou de 42–57 para 66–69 Mbps e a variância sumiu. Não afetou a negociação em 100M, que é problema separado. |
| **Ethernet do Windows a 100 Mbps** | 🟡 **Real, mas não explica tudo.** O I219-V é gigabit e negociou 100 Mbps. Só que a vazão medida foi 48.7 Mbps — metade do que o próprio link de 100 Mbps daria. Há um segundo gargalo no caminho, provavelmente o Wi-Fi do Mac ou o roteador. |
| **UDP degrada muito antes do TCP** | 🟡 **Novo e contraintuitivo.** TCP sustenta 48.7 Mbps mas UDP já perde pacote a 17 Mbps. O esperado seria o oposto. Aponta para fila/buffer no caminho (provável AP), não para falta de banda. Como SRT é UDP, é o número de 16 Mbps que vale. |
| **HEVC deixou de ser opcional** | 🟡 **Novo.** Com teto de 16 Mbps, 1080p60 em H.264 fica apertado. O `hevc_nvenc` já está validado e a 15 Mbps rende aproximadamente o que o H.264 renderia a 25. Vira dependência da Fase 2, não melhoria da Fase 7. |
| Mac sem SRT no ffmpeg | 🟢 **Resolvido** — OBS traz libsrt; `srt-live-transmit` cobre o preview. |
| **MacBook Air M4 é fanless** | 🟡 **Novo.** Decodificar 1080p60 + recodificar pra Twitch + compositar por horas vai esquentar sem ventoinha. O media engine do M4 faz codec em hardware (não é a CPU), mas throttling em live longa é risco real. **Medir na Fase 4:** `sudo powermetrics --samplers smc` durante 30 min de stream. |
| `ddagrab` não capturar o jogo | 🟡 **Bastante reduzido, mas é o que sobrou de grande.** Captura o desktop, encoda em tempo real e atravessa o SRT pela LAN — tudo verificado. O caso que importa, **jogo em fullscreen exclusivo**, segue sem resposta e só o Teste 1 responde. |
| **`ddagrab` limita em ~56–58 fps** | 🟡 **Novo.** Com a tela em movimento o pipeline não alcança 60 fps (déficit de 3–5%). O encoder não é o gargalo: sozinho faz 270 fps. Remedir com jogo real — pode melhorar ou piorar. |
| **Cadeia de filtros D3D11→CUDA não existe neste build** | 🟢 **Resolvido.** `hwmap=derive_device=cuda` e `scale_d3d11` falham; passar o `ddagrab` direto pro nvenc funciona com o mesmo desempenho. `win-test-video.ps1` corrigido. |
| Áudio loopback no Windows | 🔴 **Confirmado aberto** — o `win-doctor` rodou: a máquina **não tem nenhum device de loopback** (só Realtek onboard + NVIDIA HDMI/DP; o "NVIDIA Virtual Audio Device" é saída HDMI, não captura). A Fase 3 começa do zero, provavelmente com VB-CABLE. |
| **NVENC x versão do ffmpeg** | 🟡 **Novo.** A 9.0.1 exige driver ≥610.00 e quebra com o 591.74 instalado. Fixado na 8.1. Um `winget upgrade` desavisado reintroduz o problema. |
