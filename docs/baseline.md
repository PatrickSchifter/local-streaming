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

> O link é muito melhor do que o plano assumia. A 1.8 Gbps de PHY, um stream de
> 30–50 Mbps ocupa menos de 3% da capacidade. **A recomendação de "use cabo" do
> plano perde força** — e o MacBook Air nem tem porta Ethernet, exigiria adaptador
> USB-C. O que ainda precisa ser medido não é vazão, é **jitter sob carga**
> (ver §4, teste pendente de `iperf3`).

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

## 3. Teste 1 — vídeo ponta a ponta 🟡 metade validada

**Já provado nesta máquina** (ver §2): o script roda, o `ddagrab` captura, o
`h264_nvenc` encoda em tempo real, o SRT listener aceita conexão pelo IP da LAN e
entrega `h264 / 1080p60 / mpegts` a 30.1 Mbps. Um segundo ffmpeg fez o papel do
Mac.

**Falta o que só o Mac responde:**

**Windows:**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\win-test-video.ps1 -Gpu nvidia
```

**Mac:**

```bash
./scripts/mac-preview.sh 192.168.0.12
```

Critério: imagem da tela do Windows aparecendo na janela do ffplay.

**E o teste que mais importa:** repetir com **um jogo real em fullscreen
exclusivo**. Capturar o desktop já funciona; capturar um jogo é outra história, e
é o risco listado no §5 do plano.

## 4. Teste 2 — vazão e jitter 🟡 servidor no ar, falta o cliente

O `iperf3` **já está instalado nos dois lados**, na mesma versão 3.21.
O **servidor já está rodando no Mac** (`iperf3 -s`, porta 5201, firewall do macOS
desligado). Falta só disparar o cliente no Windows:

```powershell
iperf3 -c 192.168.0.21 -t 30              # TCP: teto do link
iperf3 -c 192.168.0.21 -u -b 25M -t 30    # UDP no bitrate-alvo real
iperf3 -c 192.168.0.21 -u -b 60M -t 30    # UDP forçando o link
```

> O teste de UDP a **25 Mbps** foi acrescentado porque é o bitrate que o projeto
> vai usar de fato (§3.3 do PLANO, revisto). O de 60 Mbps continua útil como
> teste de estresse, mas não representa a carga real.

> ⚠️ **Alvo original inalcançável.** O plano pedia "≥ 100 Mbps sustentados no TCP",
> mas o link do Windows negocia a 100 Mbps (§2), o que dá ~94 Mbps reais de TCP na
> melhor hipótese. Enquanto o cabo não for trocado, o alvo realista é **≥ 90 Mbps
> TCP**. O critério de UDP continua válido e é o que de fato importa: a 60 Mbps,
> perda < 0.1% e jitter < 5 ms.

Referência já medida: **ping para o Mac em 3 ms**, 4/4 respostas.

### Sobre o ping no sentido inverso (Mac → Windows)

`ping 192.168.0.12` a partir do Mac dá **100% de perda** — mas isso **não é
problema de rede**. O Firewall do Windows dropa ICMP echo de entrada por padrão.
A prova de que o caminho está bom: o ARP do Mac resolve o IP para
`ec:d6:8a:bb:3d:83`, exatamente o MAC do I219-V registrado em §2. O host responde
em camada 2, está online e alcançável.

Isso não afeta o projeto: o Mac é o **caller** do SRT e conecta na UDP 9000 do
Windows, que tem regra de allow explícita. Só significa que **`ping` não serve
como teste de saúde** nesse sentido — use `iperf3` ou o próprio handshake SRT.

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
| Wi-Fi não sustentar o bitrate | 🟢 **Muito menor que o previsto** — Wi-Fi 6 160 MHz a -43 dBm. Falta só medir jitter. |
| **Ethernet do Windows a 100 Mbps** | 🟡 **Novo, e inverte o gargalo.** O I219-V é gigabit mas negociou 100 Mbps — cabo ou porta do roteador. Torna a meta de "≥100 Mbps TCP" (§4) inalcançável e deixa o stream ocupando 30–50% do canal. Trocar o cabo antes do Teste 2. |
| Mac sem SRT no ffmpeg | 🟢 **Resolvido** — OBS traz libsrt; `srt-live-transmit` cobre o preview. |
| **MacBook Air M4 é fanless** | 🟡 **Novo.** Decodificar 1080p60 + recodificar pra Twitch + compositar por horas vai esquentar sem ventoinha. O media engine do M4 faz codec em hardware (não é a CPU), mas throttling em live longa é risco real. **Medir na Fase 4:** `sudo powermetrics --samplers smc` durante 30 min de stream. |
| `ddagrab` não capturar o jogo | 🟡 **Bastante reduzido, mas é o que sobrou de grande.** Captura o desktop, encoda em tempo real e atravessa o SRT pela LAN — tudo verificado. O caso que importa, **jogo em fullscreen exclusivo**, segue sem resposta e só o Teste 1 responde. |
| **`ddagrab` limita em ~56–58 fps** | 🟡 **Novo.** Com a tela em movimento o pipeline não alcança 60 fps (déficit de 3–5%). O encoder não é o gargalo: sozinho faz 270 fps. Remedir com jogo real — pode melhorar ou piorar. |
| **Cadeia de filtros D3D11→CUDA não existe neste build** | 🟢 **Resolvido.** `hwmap=derive_device=cuda` e `scale_d3d11` falham; passar o `ddagrab` direto pro nvenc funciona com o mesmo desempenho. `win-test-video.ps1` corrigido. |
| Áudio loopback no Windows | 🔴 **Confirmado aberto** — o `win-doctor` rodou: a máquina **não tem nenhum device de loopback** (só Realtek onboard + NVIDIA HDMI/DP; o "NVIDIA Virtual Audio Device" é saída HDMI, não captura). A Fase 3 começa do zero, provavelmente com VB-CABLE. |
| **NVENC x versão do ffmpeg** | 🟡 **Novo.** A 9.0.1 exige driver ≥610.00 e quebra com o 591.74 instalado. Fixado na 8.1. Um `winget upgrade` desavisado reintroduz o problema. |
