# LAN Game Streaming — Windows → Mac → OBS → Twitch

Plano de implementação faseado.

## 1. Objetivo

Jogar no PC Windows e mandar vídeo + áudio do jogo pela rede local até o Mac, onde
o OBS entra como um "source" normal e faz a live para Twitch (ou qualquer destino
que o OBS suporte).

**Resultado final esperado:** rodar um comando no Windows, abrir o OBS no Mac,
a cena já mostra o jogo com áudio sincronizado, clicar em "Start Streaming".

### Escopo

- Projeto pessoal, sem intenção comercial.
- **Sem GUI.** CLI + arquivo de config.
- **Sem código nativo.** Nada de Win32/Cocoa; o trabalho pesado é do `ffmpeg`.
- Rede local apenas. Nada de NAT traversal, TURN, relay ou internet.
- Um único par de máquinas (1 sender, 1 receiver). Sem multi-cliente.

### Não-objetivos

- Controle remoto / input do Mac de volta pro Windows (isso é Moonlight, não é o caso).
- Latência de "jogar remoto". O jogo roda e é jogado **no Windows**; o Mac só
  retransmite. Isso é a decisão de arquitetura mais importante do projeto
  (ver §3.1) — abre espaço pra priorizar qualidade e estabilidade em vez de latência.
- Empacotamento/instalador/assinatura de binário.

---

## 2. Arquitetura

```
┌────────────────────── WINDOWS (gaming) ──────────────────────┐
│                                                              │
│  Jogo (fullscreen)                                           │
│      │                                                       │
│      ├─ vídeo: ddagrab (DXGI Desktop Duplication, na GPU)    │
│      │            │                                          │
│      │            └─► NVENC / AMF / QSV  (H.264 ou HEVC)     │
│      │                                                       │
│      └─ áudio: WASAPI loopback ──► AAC / Opus                │
│                     │                                        │
│                     ▼                                        │
│              mux MPEG-TS ──► SRT listener :9000              │
└──────────────────────────────┬───────────────────────────────┘
                               │  LAN (ideal: cabo gigabit)
                               │  srt://<ip-windows>:9000
┌──────────────────────────────▼───────────────────────────────┐
│                        MAC (broadcast)                       │
│                                                              │
│   OBS ── Media Source (SRT nativo, via libobs-ffmpeg)        │
│    ├─ Mic local (offset de sync aplicado)                    │
│    ├─ Overlays / alertas / cenas                             │
│    └─► RTMP ──► Twitch / YouTube / etc.                      │
└──────────────────────────────────────────────────────────────┘
```

O projeto (`lanstream`) é um CLI Python fino que:

1. **No Windows** monta e supervisiona a linha de comando do `ffmpeg` (detecção de
   encoder, presets, bitrate, reconexão, logs).
2. **No Mac** oferece diagnóstico (`doctor`, `receive --preview`) e, na Fase 6,
   automação do OBS via `obs-websocket`.

Nada de reimplementar codec, transporte ou captura. O valor do projeto é a
**camada de orquestração e configuração** — que é justamente a parte chata de
acertar na mão toda vez.

---

## 3. Decisões técnicas

### 3.1 Latência é barata aqui

Como o jogo é jogado no Windows, o atraso Windows→Mac→Twitch **não afeta a
jogabilidade**. Ele só afeta:

- O delay total até o chat (que já é 5–20s na Twitch de qualquer jeito).
- O sync entre o microfone (capturado no Mac) e o vídeo do jogo.

Consequência prática: podemos usar buffer SRT generoso (100–200ms), B-frames,
GOP maior, lookahead — tudo que melhora qualidade por bit e que um sistema de
cloud gaming teria que recusar. **Estabilidade > latência.**

### 3.2 Transporte

| Opção | Prós | Contras | Veredito |
|---|---|---|---|
| **SRT (MPEG-TS)** | Retransmissão (ARQ), suporte nativo no OBS, sobrevive a WiFi | Um pouco de overhead | ✅ **Escolhido** |
| UDP/MPEG-TS puro | Mais simples, menor latência | Qualquer perda = artefato/glitch visível | Fallback de debug |
| RTMP | Universal | TCP, bufferiza mal, só H.264, latência ruim | ❌ |
| NDI | Plug-and-play com OBS | Consome ~100+ Mbps, sem sender NDI simples no Windows sem app extra | Plano C |
| WebRTC | Baixa latência real | Complexidade enorme (SDP, ICE, signaling) pra zero ganho aqui | ❌ |

**Modo:** Windows em `listener`, Mac em `caller`. Assim o Windows pode ficar
esperando e o OBS reconecta sozinho quando quiser, sem precisar reiniciar o sender.

### 3.3 Codec

- **HEVC (`hevc_nvenc`)** se o OBS do Mac decodificar bem — melhor qualidade/bit,
  e o Apple Silicon tem decoder HEVC em hardware. É o alvo.
- **H.264** como fallback universal.
- AV1 só se a GPU do Windows for RTX 40+ *e* o decode no Mac for M3+. Fase 7, opcional.

Bitrate em LAN cabeada não é gargalo: 30–60 Mbps CBR em 1080p60 é confortável e
deixa a imagem praticamente sem perda visível. O OBS reencoda pra Twitch depois.

### 3.4 Stack

- **Python 3.11+** — presente nos dois SOs, fácil de mexer, sem build step.
- `typer` (CLI) + `tomllib`/`tomli-w` (config) + `psutil` (supervisão de processo).
- `ffmpeg` externo (não `ffmpeg-python`): a linha de comando é gerada como lista
  de strings, logada e reproduzível na mão. Isso é essencial pra debugar.
- Sem framework, sem serviço, sem daemon. `uv` ou `pip install -e .`.

> Alternativa considerada: Go, por gerar binário único (bom no Windows). Rejeitada
> por enquanto — o ciclo de iteração em Python é mais rápido e o público é 1 pessoa.

### 3.5 Layout do repositório

```
local-streaming/
├─ PLANO.md
├─ README.md
├─ pyproject.toml
├─ lanstream.example.toml
├─ src/lanstream/
│  ├─ cli.py          # typer: send | receive | doctor | obs
│  ├─ config.py       # carga/validação do TOML + defaults por plataforma
│  ├─ ffmpeg.py       # localizar binário, montar argv, parsear stderr
│  ├─ encoders.py     # detecção NVENC/AMF/QSV + cadeia de fallback
│  ├─ sender.py       # Fase 2/3 — Windows
│  ├─ receiver.py     # Fase 4 — Mac (preview/diagnóstico)
│  ├─ supervisor.py   # Fase 5 — restart, backoff, health
│  ├─ stats.py        # Fase 7 — fps/bitrate/drops/SRT
│  └─ obs.py          # Fase 6 — obs-websocket
└─ docs/
   ├─ obs-setup.md
   └─ tuning.md
```

---

> **Status:** Fase 0 quase fechada — Mac e Windows levantados, toolchain instalado
> nas duas pontas, SRT e NVENC validados. Falta o que exige as duas máquinas ligadas
> ao mesmo tempo (Testes 1 e 2) e o teste com jogo real em fullscreen exclusivo.
> Achados e números em [`docs/baseline.md`](docs/baseline.md).

## 4. Fases

Cada fase tem critério de saída objetivo. Nenhuma fase depende de a próxima
existir — dá pra parar em qualquer uma e ainda ter algo usável.

---

### Fase 0 — Baseline manual (sem escrever código)

Provar que o caminho funciona **antes** de construir qualquer abstração em cima.
Se essa fase falhar, a arquitetura muda e nada do resto foi desperdiçado.

- [x] Levantar o hardware: GPU do Windows (NVIDIA/AMD/Intel), chip do Mac, se a
      conexão entre os dois é cabo ou WiFi.
- [x] Instalar `ffmpeg` full build nos dois lados (Windows: gyan.dev / BtbN;
      Mac: `brew install ffmpeg`). Confirmar `ffmpeg -encoders | grep nvenc` e
      `ffmpeg -filters | grep ddagrab` no Windows.
- [x] Descobrir o IP local do Windows e liberar a porta 9000/UDP no Windows Firewall.
- [ ] **Teste 1 — só vídeo, na mão.** No Windows:
      `ffmpeg -f lavfi -i ddagrab=0:framerate=60 -c:v h264_nvenc -preset p5 -tune ll -b:v 30M -f mpegts "srt://0.0.0.0:9000?mode=listener"`
      No Mac: `ffplay "srt://<IP-WIN>:9000?mode=caller"`.
- [ ] **Teste 2 — dentro do OBS.** Media Source com a mesma URL SRT.
- [ ] Medir: throughput real (`iperf3` entre as máquinas), latência ponta-a-ponta
      (cronômetro na tela do Windows filmado pela cena do OBS), estabilidade em 10min.
- [x] Registrar tudo em `docs/baseline.md` — os números viram a referência de regressão.

**Saída:** imagem do jogo aparecendo dentro do OBS no Mac, sem áudio, estável por
10 minutos, com os comandos exatos anotados.

**Risco identificado aqui:** se `ddagrab` não capturar o jogo (alguns títulos em
exclusive fullscreen ou com anti-cheat agressivo), a alternativa é `gdigrab` (mais
lento) ou rodar OBS no Windows só como capturador. Descobrir isso na Fase 0, não na 5.

---

### Fase 1 — Esqueleto do projeto

- [ ] `git init`, `pyproject.toml`, `src/lanstream/`, ruff + formatação.
- [ ] `lanstream.example.toml` com todas as chaves comentadas
      (`[network] host/port/latency_ms`, `[video] width/height/fps/bitrate/codec/encoder`,
      `[audio] device/bitrate`, `[paths] ffmpeg`).
- [ ] `config.py`: carrega `./lanstream.toml` → `~/.config/lanstream/config.toml`
      → defaults; valida e dá erro legível (não stack trace) quando falta chave.
- [ ] `ffmpeg.py`: localizar binário (config > `PATH` > locais conhecidos), rodar
      `-version`, extrair versão e lista de encoders.
- [ ] `lanstream doctor`: imprime SO, versão do ffmpeg, encoders de hardware
      disponíveis, IPs locais, e se a porta está livre/alcançável. Funciona nos dois SOs.
      No Mac deve checar `srt-live-transmit` (e não o protocolo `srt` do ffmpeg,
      que não existe lá). Portar a lógica de `scripts/win-doctor.ps1`.

**Saída:** `lanstream doctor` roda no Mac e no Windows e mostra um diagnóstico correto.

---

### Fase 2 — Sender: vídeo (Windows)

- [ ] `encoders.py`: detectar e escolher encoder por cadeia de fallback
      `hevc_nvenc → h264_nvenc → hevc_amf → h264_amf → hevc_qsv → h264_qsv → libx264`,
      com override no config.
- [ ] `sender.py`: montar o argv do ffmpeg a partir da config —
      `ddagrab` (monitor selecionável, framerate, `-c:v` + `-preset`/`-rc cbr`
      `-b:v`/`-maxrate`/`-bufsize`, `-g` = 2×fps, `-f mpegts`, URL SRT listener).
- [ ] Escala opcional na GPU (`scale_cuda`/`scale_d3d11`) — jogar em 1440p e
      transmitir 1080p sem custo de CPU.
- [ ] `lanstream send` — inicia, faz streaming do stderr do ffmpeg para o log,
      e encerra limpo no Ctrl+C (SIGINT propagado, sem ffmpeg órfão segurando a porta).
- [ ] `lanstream send --dry-run` imprime o comando montado sem executar.

**Saída:** `lanstream send` no Windows + Media Source no Mac = jogo na tela do OBS.

---

### Fase 3 — Sender: áudio do jogo

O ponto mais chato do projeto inteiro. O `ffmpeg` **não tem** captura WASAPI
loopback nativa no Windows, então precisa de um device intermediário.

- [ ] Avaliar as opções, em ordem de preferência:
      1. **VB-Audio Cable** (ou VoiceMeeter) — cria um device virtual; saída do
         jogo vai pro cable, `ffmpeg -f dshow -i audio="CABLE Output"` captura.
         Cuidado: por padrão você deixa de ouvir o áudio → habilitar "Listen to
         this device" ou usar o VoiceMeeter pra duplicar.
      2. `virtual-audio-capturer` do pacote screen-capture-recorder — loopback
         direto do device default, sem mexer no roteamento. Mais simples, porém
         projeto antigo.
      3. Fallback: áudio via OBS no Windows (descartado se 1 ou 2 funcionar).
- [ ] Adicionar a entrada de áudio no argv, encodar em AAC 160–320k, muxar no
      mesmo MPEG-TS.
- [ ] `lanstream doctor --audio` lista os devices dshow disponíveis (`-list_devices true`).
- [ ] Verificar A/V sync: gravar um teste com claquete visual+sonora e conferir
      no OBS. Se houver drift, aplicar `-itsoffset` no lado do sender.

**Saída:** áudio do jogo chegando no OBS, sincronizado, sem drift depois de 20 minutos.

---

### Fase 4 — Lado Mac e integração com OBS

- [ ] `lanstream receive --preview`: **`srt-live-transmit | ffplay`** (o ffmpeg do
      Homebrew não tem libsrt — ver `docs/baseline.md`). É a ferramenta de
      diagnóstico pra responder "o problema é a rede ou o OBS?" em 5 segundos.
      Já validado em loopback na Fase 0.
- [ ] `docs/obs-setup.md` com a receita exata:
      - Media Source, "Local File" desmarcado, Input = URL SRT com
        `?mode=caller&latency=...`, `Input Format = mpegts`.
      - Desmarcar "Restart playback when source becomes active",
        marcar "Close file when inactive" = **off** (senão o SRT cai ao trocar de cena).
      - "Use hardware decoding when available" = **on** (VideoToolbox no Apple Silicon).
      - Network buffering em 0 (o buffer já é do SRT).
      - Escala/ancoragem da fonte na cena.
- [ ] Mic no Mac: medir o offset em relação ao vídeo e aplicar **Sync Offset**
      nas propriedades avançadas de áudio do OBS. Documentar o valor medido.
- [ ] Definir a config de saída pra Twitch (encoder Apple VT H.264, 6000–8000 kbps,
      keyframe 2s) e deixar num perfil do OBS.

**Saída:** cena do OBS completa (jogo + mic + overlays), stream de teste privado
na Twitch rodando 15 minutos sem dropped frames.

---

### Fase 5 — Robustez

Aqui o projeto para de ser "dois comandos" e vira algo que aguenta uma sessão real.

- [ ] `supervisor.py`: se o ffmpeg morrer, reiniciar com backoff exponencial e
      teto; logar o motivo. Nunca deixar processo órfão segurando a porta 9000.
- [ ] Detectar mudança de resolução/refresh do monitor (jogo entrando em fullscreen
      exclusivo) — o `ddagrab` costuma quebrar aí. Reiniciar a captura em vez de morrer.
- [ ] Logs rotativos em arquivo + `--verbose` no console.
- [ ] `lanstream send --watch`: fica no ar esperando o OBS conectar/reconectar,
      sem precisar reiniciar nada do lado do Windows.
- [ ] Auto-start opcional no Windows: gerar a entrada do Task Scheduler /
      atalho na pasta Startup via `lanstream install-autostart`.
- [ ] (Opcional) Anúncio mDNS/Bonjour do sender, pra não precisar fixar IP.
      Só vale a pena se o IP do Windows mudar de fato — senão, DHCP reservation
      no roteador resolve com zero código.

**Saída:** desligar o Wi-Fi/cabo por 30s e religar — o stream volta sozinho, sem
intervenção nas duas máquinas.

---

### Fase 6 — Automação do OBS (`obs-websocket`)

- [ ] `obs.py` com `obsws-python` (obs-websocket v5, já embutido no OBS 28+).
- [ ] `lanstream obs status` — conectado?, cena atual, streaming ativo, dropped frames.
- [ ] `lanstream obs go-live` — verifica que o SRT já está chegando **antes** de
      dar start no stream (evita ir ao ar com tela preta), troca pra cena de jogo,
      inicia a transmissão.
- [ ] `lanstream obs stop` — encerra a live e volta pra cena "Ausente".
- [ ] (Opcional) Um comando único no Windows que dispara o `go-live` no Mac via
      HTTP/SSH — assim a sessão inteira começa sem tocar no Mac.

**Saída:** um comando começa a live inteira; outro encerra.

---

### Fase 7 — Qualidade e tuning

- [ ] `stats.py`: parsear o stderr do ffmpeg (fps, bitrate, speed, dup/drop) e o
      relatório de estatísticas do SRT (pacotes perdidos/retransmitidos), imprimir
      resumo periódico.
- [ ] Presets nomeados no config: `quality` (HEVC 1080p60 50Mbps), `balanced`,
      `wifi` (bitrate menor, latência SRT maior, H.264). `lanstream send --preset wifi`.
- [ ] Testar 1440p e 120fps; achar o teto do link e do decoder do Mac.
- [ ] Cores: garantir que não há shift (full vs limited range, BT.709). Testar com
      uma imagem de referência e comparar pixel a pixel entre as duas máquinas.
- [ ] Avaliar AV1 se o hardware permitir.
- [ ] `docs/tuning.md` com a tabela do que mexer pra cada sintoma
      (macroblocos → bitrate; travadas → latência SRT; sync ruim → offset; etc.).

**Saída:** dois ou três presets validados e uma tabela de troubleshooting.

---

### Fase 8 — Documentação e encerramento

- [ ] `README.md`: setup do zero nas duas máquinas em menos de 10 passos.
- [ ] Checklist de "antes de ir ao ar".
- [ ] Seção de problemas conhecidos com os erros reais encontrados no caminho.

---

## 5. Riscos e mitigações

| Risco | Impacto | Mitigação |
|---|---|---|
| `ddagrab` não captura o jogo (fullscreen exclusivo / anti-cheat) | Alto — quebra a premissa | Testar na Fase 0 com os jogos reais. Fallback: forçar borderless windowed, ou usar OBS no Windows como capturador enviando SRT. |
| Áudio loopback no Windows exige software de terceiro | Médio | Fase 3 isolada, três opções mapeadas. |
| Media Source do OBS instável com SRT longo prazo | Médio | `receive --preview` isola a causa; plano B é ffmpeg→NDI (DistroAV) no Mac. |
| **MacBook Air M4 é fanless** | 🟡 Médio | **Novo (Fase 0).** Live longa = decode + reencode + composição sem ventoinha. Medir throttling com `powermetrics` na Fase 4; se ocorrer, baixar resolução de saída ou o preset do encoder. |
| ~~ffmpeg do Mac sem SRT~~ | 🟢 Resolvido | **Fase 0:** fórmula do Homebrew não linka libsrt, mas o OBS traz o próprio `libsrt.dylib` e `srt-live-transmit` cobre o preview. |
| ~~WiFi não sustenta o bitrate~~ | 🟢 Baixo | **Revisto na Fase 0:** link é Wi-Fi 6, 5 GHz 160 MHz, -43 dBm, 1814 Mbps PHY. O MacBook Air nem tem porta Ethernet. Falta medir só jitter sob carga. Ver `docs/baseline.md`. |
| Drift de A/V ao longo de horas | Médio | Testes longos nas Fases 3 e 4; `-itsoffset` e sync offset do OBS. |
| Mac gargalando ao decodificar + reencodar pra Twitch | Médio | Decode por hardware (VideoToolbox) + encoder Apple VT na saída; medir na Fase 4. |
| Escopo crescendo (multi-monitor, multi-cliente, GUI) | Baixo | Está em "Não-objetivos". |

---

## 6. Plano B (se o custo não compensar)

Se em qualquer ponto o esforço deixar de valer:

**Sunshine (Windows) + Moonlight (Mac) + Window Capture no OBS.** Zero código,
funciona hoje, com encoder de hardware e áudio resolvido. O custo é a captura de
janela no macOS (mais pesada), a borda/overlay do Moonlight na imagem, e nenhum
controle fino sobre o pipeline.

Vale como comparação honesta ao fim da Fase 2: se o resultado do `lanstream` não
estiver claramente melhor, o projeto virou aprendizado e o Plano B assume.
