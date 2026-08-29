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

## 2. Windows (sender) — ⏳ pendente

Não consigo inspecionar essa máquina daqui. Rode e cole a saída:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\win-doctor.ps1
```

A preencher:

| Item | Valor |
|---|---|
| GPU / driver | _?_ |
| Encoders de HW disponíveis | _?_ (nvenc / amf / qsv) |
| `ddagrab` presente | _?_ |
| SRT no ffmpeg | _?_ |
| IP na LAN | _?_ |
| Link do adaptador | _?_ (cabo gigabit ou Wi-Fi) |
| Devices de áudio dshow | _?_ |
| Resolução / refresh do monitor | _?_ |

### Se o ffmpeg não estiver instalado

```powershell
winget install --id=Gyan.FFmpeg -e
```

Precisa ser o build **full** (gyan.dev ou BtbN), não o `essentials` — o
`essentials` vem **sem SRT**, que é exatamente o que o projeto usa.
Feche e reabra o terminal depois de instalar, pro PATH atualizar.

### Firewall (uma vez, PowerShell como Administrador)

```powershell
New-NetFirewallRule -DisplayName "lanstream SRT" -Direction Inbound `
  -Protocol UDP -LocalPort 9000 -Action Allow -Profile Private
```

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
| Mac sem SRT no ffmpeg | 🟢 **Resolvido** — OBS traz libsrt; `srt-live-transmit` cobre o preview. |
| **MacBook Air M4 é fanless** | 🟡 **Novo.** Decodificar 1080p60 + recodificar pra Twitch + compositar por horas vai esquentar sem ventoinha. O media engine do M4 faz codec em hardware (não é a CPU), mas throttling em live longa é risco real. **Medir na Fase 4:** `sudo powermetrics --samplers smc` durante 30 min de stream. |
| `ddagrab` não capturar o jogo | 🔴 **Ainda aberto** — é o maior risco do projeto e só o teste no Windows responde. |
| Áudio loopback no Windows | 🔴 **Ainda aberto** — o `win-doctor` vai dizer se já existe algum device virtual. |
