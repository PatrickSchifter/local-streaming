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

### Software — praticamente nada instalado ainda

| Ferramenta | Estado |
|---|---|
| ffmpeg | ❌ **ausente** (winget oferece `Gyan.FFmpeg` 9.0.1) |
| OBS Studio | ❌ ausente (não é necessário deste lado) |
| iperf3 | ❌ ausente — bloqueia o Teste 2 (§4) |
| Python | ❌ só o stub da Microsoft Store, não é Python real |
| uv | ❌ ausente |

Sem ffmpeg, **4 checagens do `win-doctor` ficaram sem resposta** e continuam pendentes:

| Item | Valor |
|---|---|
| Encoders de HW disponíveis | ⏳ não verificado — mas a RTX 3060 (Ampere) tem **NVENC 7ª geração**, H.264 + HEVC. Sem encode AV1 (só decode). |
| `ddagrab` presente | ⏳ não verificado |
| SRT no ffmpeg | ⏳ não verificado |
| Devices de áudio dshow | ⏳ não verificado |

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

### Firewall

Regra `lanstream SRT` (UDP 9000) **ausente**. Rodar uma vez como Administrador:

```powershell
New-NetFirewallRule -DisplayName "lanstream SRT" -Direction Inbound `
  -Protocol UDP -LocalPort 9000 -Action Allow -Profile Private
```

### Próximos passos deste lado

1. `winget install --id=Gyan.FFmpeg -e` (build full — o `essentials` não tem SRT).
2. Reabrir o terminal e rodar `scripts\win-doctor.ps1` de novo para fechar as 4
   linhas pendentes.
3. `winget install --id=ar51an.iperf3` (ou equivalente) para o Teste 2.
4. Criar a regra de firewall.
5. Investigar o link de 100 Mbps.

---

## 3. Teste 1 — vídeo ponta a ponta ⏳ pendente

**Windows** (ajuste `-Gpu` conforme o `win-doctor` reportar):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\win-test-video.ps1 -Gpu nvidia
```

**Mac:**

```bash
./scripts/mac-preview.sh <IP-DO-WINDOWS>
```

Critério: imagem da tela do Windows aparecendo na janela do ffplay.

## 4. Teste 2 — vazão e jitter ⏳ pendente

**Mac** (servidor): `iperf3 -s`
**Windows** (cliente): `iperf3 -c 192.168.0.21 -t 30`
Depois, o que realmente importa pra streaming — **UDP com jitter e perda**:
`iperf3 -c 192.168.0.21 -u -b 60M -t 30`

Alvo: ≥ 100 Mbps sustentados no TCP; no UDP a 60 Mbps, perda < 0.1% e jitter < 5 ms.

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
| `ddagrab` não capturar o jogo | 🔴 **Ainda aberto** — é o maior risco do projeto e só o teste no Windows responde. |
| Áudio loopback no Windows | 🔴 **Confirmado aberto** — o `win-doctor` rodou: a máquina **não tem nenhum device de loopback** (só Realtek onboard + NVIDIA HDMI/DP; o "NVIDIA Virtual Audio Device" é saída HDMI, não captura). A Fase 3 começa do zero, provavelmente com VB-CABLE. |
