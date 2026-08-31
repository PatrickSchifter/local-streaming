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

**Bitrate — revisto na Fase 0.** A intuição inicial ("quanto mais, melhor") ignora
que **o OBS reencoda pra Twitch a 6–8 Mbps**. O stream da LAN não precisa ser
bonito, precisa ser *transparente o bastante pra que o segundo encode não componha
artefato em cima do primeiro*. A 1080p60, HEVC a 20 Mbps já está ~3x acima do
que a saída da Twitch consegue mostrar — subir pra 50 Mbps não muda um pixel do
que o espectador vê, só ocupa canal.

> 🔴 **A medição depois apertou mais esse número.** O `iperf3` mostrou que a rede
> perde pacote em UDP acima de **16 Mbps** (`docs/baseline.md` §4): 1.6% a 20 Mbps,
> 4.4% a 25. Então **20–25 Mbps não cabe** — não por qualidade, por transporte.
>
> O raciocínio acima não muda, só fica mais fácil de aceitar: se 20 Mbps já era 3x
> mais do que a Twitch mostra, **15 Mbps ainda é ~2x**. O corte não custa nada que
> o espectador consiga ver.

Alvo adotado: **15 Mbps HEVC** (ou ~20 H.264, se HEVC falhar no OBS do Mac), CBR.
Medido: a 15M o stream fica cravado em 15.07 Mbps com speed 0.993x e 58 fps.
Ver §5 sobre o link — e note que **HEVC deixou de ser preferência e virou
requisito**, porque é ele que faz 1080p60 caber em 15 Mbps.

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

> **Status:** ✅ **Fase 0 concluída** (2026-08-29). Jogo real capturado, 10 min
> com perda zero, e OBS renderizando a 60 fps sem frame descartado. Config de
> produção: `hevc_nvenc 15M` + buffer SRT 1.2 s.
> Achados e números em [`docs/baseline.md`](docs/baseline.md).
>
> ✅ **Fase 1 concluída** (2026-08-29). `lanstream doctor` roda no Mac e no
> Windows com diagnóstico correto nos dois: nove checagens, nove OK, código de
> saída 0 no Windows. A config valida com erro legível de uma linha.
> Registro em [`docs/fase1.md`](docs/fase1.md).
> O débito do `[network] host` foi quitado no mesmo dia: `host` (o sender, que as
> URLs precisam) e `peer` (a outra ponta, que o alcance precisa) são campos
> separados, e a correção rendeu uma checagem nova — o doctor agora percebe que o
> IP do sender mudou (`docs/fase1.md` §1).
>
> ✅ **Fase 2 CONCLUÍDA** (2026-08-30). O `lanstream send` monta no Windows
> exatamente o comando que a Fase 0 validou na mão, o `CTRL_C_EVENT` do console
> encerra o ffmpeg em 0.27–0.67 s sem órfão na porta 9000, e a rodada real
> entregou **Resident Evil 2 remake para o OBS do Mac: 3 minutos, 57.1 fps
> instantâneos, 14.5–15.2 Mbps sustentados, `drop=0` em 10.056 frames**. É a
> primeira rodada do projeto que de fato estressa o teto de ~17 Mbps do
> `baseline` §4e — o T1 pedia isso desde 29/08 e nunca tinha conseguido.
> Registro em [`docs/fase2.md`](docs/fase2.md). Os contadores do lado do Mac
> foram coletados na mesma rodada e **confirmam** o sender em vez de contradizê-lo
> (mídia/relógio 0.9997, zero frame descartado pelo OBS, imagem conferida por
> captura) — o buraco do `baseline` §4d, sender feliz com receptor sofrendo, não
> se repetiu.
>
> ⛔ **A fase produziu uma restrição:** a captura só funciona com o jogo em
> **borderless**. Em fullscreen exclusivo o `ddagrab` morre com
> `DXGI_ERROR_ACCESS_LOST` (`docs/fase2.md` §8) — e, ao contrário do que este
> plano supunha, **não é mudança de resolução**: o desktop seguiu 1920x1080@60.
> Ver o item corrigido na Fase 5.

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
- [x] **Teste 1 — só vídeo, na mão.** No Windows:
      `ffmpeg -f lavfi -i ddagrab=0:framerate=60 -c:v h264_nvenc -preset p5 -tune ll -b:v 30M -f mpegts "srt://0.0.0.0:9000?mode=listener"`
      No Mac: `ffplay "srt://<IP-WIN>:9000?mode=caller"`.
- [x] **Teste 2 — dentro do OBS.** Media Source com a mesma URL SRT. (`baseline` §5)
- [x] Medir: throughput real (`iperf3` entre as máquinas), latência ponta-a-ponta
      (cronômetro na tela do Windows filmado pela cena do OBS), estabilidade em 10min.
- [x] Registrar tudo em `docs/baseline.md` — os números viram a referência de regressão.

**Saída:** imagem do jogo aparecendo dentro do OBS no Mac, sem áudio, estável por
10 minutos, com os comandos exatos anotados.

**Risco identificado aqui:** se `ddagrab` não capturar o jogo (alguns títulos em
exclusive fullscreen ou com anti-cheat agressivo), a alternativa é `gdigrab` (mais
lento) ou rodar OBS no Windows só como capturador. Descobrir isso na Fase 0, não na 5.

---

### Fase 1 — Esqueleto do projeto

- [x] `git init`, `pyproject.toml`, `src/lanstream/`, ruff + formatação.
      Instalação: `uv venv && uv pip install -e ".[dev]"`. `ruff check src/` limpo.
- [x] `lanstream.example.toml` com todas as chaves comentadas. Os valores do
      arquivo são exatamente os defaults do código — verificado com
      `lanstream config show -c lanstream.example.toml`, que devolve o mesmo TOML.
      Cada número traz a referência do `baseline` que o justifica.
- [x] `config.py`: carrega `--config` → `./lanstream.toml` →
      `~/.config/lanstream/config.toml` → defaults (a primeira que existir vence;
      não há merge). Chave desconhecida sugere a parecida, tipo errado e faixa
      inválida têm mensagem própria, e nada disso sai como stack trace — sai como
      uma linha e código 2.
      A conversão de unidade do `latency` mora só aqui (`url_for_ffmpeg` em µs,
      `url_for_srt_live_transmit` em ms), que é a pegadinha de três variantes do
      `baseline` §5.
- [x] `ffmpeg.py`: localiza o binário (config > `PATH` > locais conhecidos — o
      instalador do Windows não atualiza o PATH da sessão aberta), extrai versão e
      build, e consulta encoders/filtros/protocolos sob demanda. Guarda a cadeia de
      fallback da Fase 2 e avisa sobre a incompatibilidade ffmpeg 9.x × driver
      591.74 (`baseline` §2).
- [x] `lanstream doctor`: SO e papel, config em uso, ffmpeg, encoders de hardware,
      `ddagrab` e protocolo SRT (Windows), `srt-live-transmit` e `ffplay` (Mac),
      regra de firewall, IPs locais, porta 9000/UDP livre, alcance até o sender, e
      as três URLs já com a unidade certa. Sai 1 se houver FALHA.
      Portou `scripts/win-doctor.ps1` e **corrigiu um falso negativo dele**: o
      alcance não é testado por `ping` — o Firewall do Windows dropa ICMP echo e a
      máquina online aparecia como morta (`baseline` §4). A prova de vida é o ARP
      resolver o MAC.
- [x] **Rodar o `doctor` no Windows.** Rodado em 29/08: nove checagens, nove OK,
      código de saída 0. ffmpeg ainda 8.1, `hevc_nvenc` escolhido, `ddagrab` e SRT
      presentes, firewall e IP como a Fase 0 deixou (`docs/fase1.md` §1).

**Saída:** `lanstream doctor` roda no Mac e no Windows e mostra um diagnóstico correto.

> **Onde está:** ✅ **Batido nos dois lados.** Mac — diagnóstico correto,
> inclusive reconhecendo que a ausência de SRT no ffmpeg do Homebrew é o esperado
> e não um defeito. ✅ Windows — a rodada real confirmou o que a execução forçada
> só sugeria: o ramo Windows não apenas não quebra, ele acerta os nove itens que a
> Fase 0 levantou na mão.
>
> ✅ **Débito quitado antes de começar:** o `[network] host` foi separado em `host`
> (o sender — é o que as URLs precisam, e vale igual nas duas máquinas) e `peer`
> (a outra ponta, só para o teste de alcance). De quebra, conferir que o `host` é
> mesmo um IP da máquina local virou detector de troca de IP pelo DHCP, que antes
> só apareceria com o OBS na tela preta (`docs/fase1.md` §1).

---

### Fase 2 — Sender: vídeo (Windows)

- [x] **Separar `[network] host` em `host` + `peer`.** Feito antes do resto: a URL
      passa a ser gerada para valer aqui, e um campo ambíguo alimentando-a era
      defeito esperando acontecer. As quatro combinações de `host`/`peer` nos dois
      SOs foram exercitadas (`docs/fase1.md` §1).
- [x] `encoders.py`: detectar e escolher encoder por cadeia de fallback
      `hevc_nvenc → h264_nvenc → hevc_amf → h264_amf → hevc_qsv → h264_qsv → libx264`,
      com override no config. Não abre processo nenhum — recebe o conjunto de
      encoders e decide —, o que permite montar o comando do Windows a partir do
      Mac. Trouxe junto **as flags por família**: `-preset p5` (NVENC),
      `-quality quality` (AMF), `-preset medium` (QSV), `-preset veryfast` (x264).
- [x] **`[video] preset` perdeu o default global.** Consequência do item acima: o
      `preset = "p5"` só estava certo porque esta máquina tem NVIDIA. Agora vazio
      = o default da família, e um valor explícito é conferido contra ela — o
      ffmpeg aceitaria `-preset veryfast` num `hevc_nvenc` e cairia num default
      silencioso (`docs/fase2.md` §2). O `doctor` ganhou a checagem.
- [x] `sender.py`: montar o argv do ffmpeg a partir da config —
      `ddagrab` (monitor selecionável, framerate, `-c:v` + `-preset`/`-rc cbr`
      `-b:v`/`-maxrate`/`-bufsize`, `-g` = 2×fps, `-f mpegts`, URL SRT listener).
      O comando montado é **idêntico ao do `win-test-video.ps1` da Fase 0**, com
      uma flag a mais (`-nostdin`, porque agora há um supervisor no meio).
- [x] ~~Escala opcional na GPU (`scale_cuda`/`scale_d3d11`)~~ — **não se aplica,
      por dois motivos independentes:** o build não deriva device CUDA do D3D11
      (`scale_cuda` dá ENOSYS, `scale_d3d11` não configura o pad — baseline §2) e
      não há o que escalar, porque o `ddagrab` captura o monitor e o monitor é
      1080p60. Sobraria escalar na CPU, que é o custo que o item existia para
      evitar (`docs/fase2.md` §3). Reavaliar só se o monitor mudar.
- [x] `lanstream send` — inicia, faz streaming do stderr do ffmpeg para o log,
      e encerra limpo no Ctrl+C (SIGINT propagado, sem ffmpeg órfão segurando a porta).
      Medido com fonte sintética e SIGINT no grupo de processos: sai em 0.12 s,
      sem sobrevivente (`docs/fase2.md` §4). O ffmpeg **não** vai para um grupo
      próprio — é o que faz o Ctrl+C chegar nele. **Confirmado no Windows real**
      em 30/08 com o `CTRL_C_EVENT` do console: 0.27–0.67 s, sem órfão, e o
      `send` seguinte sobe na hora (`docs/fase2.md` §5).
- [x] **Critério de saída batido:** rodada real com o OBS do Mac como Media
      Source — RE2 remake em borderless, 3 min, 57.1 fps instantâneos, 14.5–15.2
      Mbps, `speed` 1.000x, `drop=0`, imagem confirmada do outro lado. Os
      contadores do lado do Mac (`RCV-DROPPED`, decode) não foram coletados; fica
      como dívida, não como bloqueio (`docs/proximos-testes.md` §F2.3).
- [x] `lanstream send --dry-run` imprime o comando montado sem executar. Roda
      fora do Windows de propósito: é como se confere o comando de lá sentado
      aqui, e nesse caso o ffmpeg local não é consultado (a resposta dele seria
      pior que nenhuma).
- [x] **Rodar o `send` no Windows** — quatro dos cinco passos, os que não
      dependem do Mac (30/08): o `doctor` dá 11 OK, o comando montado é o da
      Fase 0, o `CTRL_C_EVENT` encerra limpo em 0.27–0.67 s e dois `send`
      seguidos sobem sem `Address already in use`.
- [x] **O doctor passou a distinguir as duas causas de `host` inválido.** A
      rodada de 30/08 falhou primeiro por config velha (`host` = IP do Mac, a
      semântica anterior ao 010d763) e a mensagem dizia "o IP mudou" — mandava
      caçar a coisa errada. Agora `host == peer` é diagnosticado pelo nome e o
      caso ambíguo lista as duas hipóteses (`docs/fase2.md` §7).
- [x] **F2.3 — a rodada com o OBS do Mac.** Rodou em 30/08 e fechou o critério
      de saída. Os contadores do lado do Mac, que ficaram como dívida na primeira
      escrita, foram coletados por `obs-websocket` durante a própria corrida:
      mídia/relógio 0.9997 em 60 s, zero frame descartado pelo OBS, render 60.00
      fps, CPU 10.7–11.1%. As duas pontas concordam, inclusive no fim
      (`docs/proximos-testes.md` §F2.3). O `RCV-DROPPED` do libsrt continua não
      coletado, e agora com motivo: o obs-websocket não expõe as estatísticas
      internas do SRT — quem as tem é o `receive --preview` da Fase 4.

**Saída:** `lanstream send` no Windows + Media Source no Mac = jogo na tela do OBS.

> **Onde está:** ✅ **Fechada em 30/08, com os cinco passos.** O `CTRL_C_EVENT`
> chega no ffmpeg e ele sai escrevendo o trailer, sem `terminate` e sem segurar a
> porta; e o jogo real chegou no OBS do Mac medido dos dois lados.
> **A fase produziu uma restrição:** só **borderless**. Em fullscreen exclusivo a
> captura morre em ~4 s com `DXGI_ERROR_ACCESS_LOST` (§F2.3-bis) — é limitação da
> Desktop Duplication, não do código, e vale para toda sessão daqui em diante.

---

### Fase 3 — Sender: áudio do jogo

O ponto mais chato do projeto inteiro. O `ffmpeg` **não tem** captura WASAPI
loopback nativa no Windows, então precisa de um device intermediário.

- [x] **A ordem de preferência mudou, e o motivo não é técnico.** O áudio precisa
      continuar saindo pela caixa de som do Windows — quem está jogando está
      sentado nela —, e isso reprova o VB-CABLE puro, que emudece o jogo para o
      jogador. A ordem agora é (`docs/fase3.md` §1):
      1. **Mixagem estéreo (Stereo Mix)** do Realtek — custo zero, é só habilitar
         em `mmsys.cpl > Gravação > Mostrar dispositivos desativados`. Pode não
         existir no driver, e o `Win32_SoundDevice` do baseline **não** responde
         isso: ele lista placas, não entradas desabilitadas.
      2. **VB-CABLE** + "Ouvir este dispositivo" — driver e reboot, e o "Ouvir"
         põe latência no ouvido de quem joga.
      3. **VoiceMeeter**, se essa latência atrapalhar: é o que duplica direito.
      4. `virtual-audio-capturer` — não mexe no roteamento, mas é projeto parado.
- [x] Entrada de áudio no argv, AAC 160k, muxada no mesmo MPEG-TS. Com o áudio
      desligado o comando sai **byte a byte igual** ao da Fase 2 (verificado com
      `diff`), o que faz do `send --no-audio` um bisect de verdade. Junto vieram
      `-audio_buffer_size` (o default do dshow é ~500 ms, que sozinho seria a
      dessincronia inteira) e `-thread_queue_size` (duas entradas ao vivo).
- [x] `lanstream doctor --audio` lista os devices dshow **classificados** em
      loopback / microfone / desconhecido, e sem device nenhum imprime a ordem de
      tentativa acima. O parser aguenta os dois formatos de listagem que existem.
- [x] **A forma do comando validada num ffmpeg de verdade, sem sair do Mac.**
      `scripts/av-sync.py ensaio` troca só o que não existe fora do Windows
      (ddagrab, dshow, NVENC) e roda o resto: duas trilhas no TS, 48 kHz estéreo,
      deriva -0.0 ms em 200 s. Não prova nada sobre a captura — prova que o
      comando não está torto.
- [x] **A/V sync virou número, não impressão.** Claquete de 100 ms a cada 5 s,
      `blackdetect` × `silencedetect`, com o viés do método medido (~12 ms) e
      offset separado de deriva. O sinal do `-itsoffset` foi **medido**: positivo
      atrasa o áudio (`docs/fase3.md` §3).
- [ ] **F3 no Windows** — o bloqueio é de hardware: a máquina não tem device de
      captura nenhum (`baseline` §7). Protocolo em
      [`docs/proximos-testes.md`](docs/proximos-testes.md) §F3; o passo 1 custa
      2 minutos e pode encerrar a fase sem instalar nada.
- [ ] Se aparecer deriva (e não offset), o caminho é `aresample=async=1` — e aí
      é item da Fase 7, com a medição junto, não um knob solto aqui.

**Saída:** áudio do jogo chegando no OBS, sincronizado, sem drift depois de 20 minutos.

> **Onde está:** 🟡 **Áudio no ar e sem furos; falta o sincronismo fechar.**
> O device é o `virtual-audio-capturer` (o Stereo Mix não serve nesta máquina —
> a saída é HDMI e ele é da onboard, `docs/fase3.md` §1). Com `buffer_ms = 200` a
> continuidade ficou boa (cobertura de 55% → 80–87%) e com `resync = true` a
> rampa acabou (62 min limpos contra ~45 min até o OBS reiniciar o áudio sozinho).
>
> **O que trava:** o deslocamento constante **muda a cada execução do `send`** —
> de −51 ms a +879 ms ao longo de 31/08, estável em ±25 ms dentro de cada rodada.
> `offset_ms` é constante de config e o que ele precisa corrigir não é
> (`docs/fase3.md` §13). O teste que decide são três gravações locais de 60 s no
> Windows, reiniciando o `send` entre elas.
>
> A fase segue aberta **sem bloquear a Fase 4**: o áudio chega, o vídeo chega, e
> o que falta é um número que ainda não é constante.

---

### Fase 4 — Lado Mac e integração com OBS

- [x] `lanstream receive --preview`: **`srt-live-transmit | ffplay`** (o ffmpeg do
      Homebrew não tem libsrt — ver `docs/baseline.md`). É a ferramenta de
      diagnóstico pra responder "o problema é a rede ou o OBS?" em 5 segundos.
      Testado contra um listener local nos dois casos que importam: conexão
      saudável seguida de queda do sender (sai na hora, sem órfão) e ninguém
      escutando (avisa, e diz as **duas** causas possíveis).
      - `-a no` e `-autoexit` entraram por medição: sem eles o preview congela no
        último quadro quando o sender cai, e a ferramenta que existe para dizer
        "o sender caiu" fica muda exatamente aí.
      - ⛔ **Sem `--stats`.** A ideia era pagar a dívida do `RCV-DROPPED` da Fase 2
        aqui, e **não dá com esta ferramenta**: com a saída em `file://con` ela
        recusa `-s` ("would result in mixing the data and text info"), o
        `-statsout` é aceito e não escreve nada nos três formatos, e
        `file:///dev/null` é "Unsupported target type". Ou se consome o stream, ou
        se leem os contadores. A dívida continua aberta, agora com motivo medido.
- [x] `docs/obs-setup.md` com a receita exata — escrita a partir do OBS **em
      execução**, lido por `obs-websocket`, e não transcrita de menu. Traz junto
      as três coisas que custaram tempo: o arquivo de cena no disco é o que o OBS
      *carregou* e não o que está valendo; a monitoração tem latência própria e
      não entra na gravação; e as duas linhas de log (`audio buffering` e
      `audio is lagging`) que diagnosticam áudio melhor que uma gravação.
      Detalhes originais do item:
      - Media Source, "Local File" desmarcado, Input = URL SRT com
        `?mode=caller&latency=...`, `Input Format = mpegts`.
      - Desmarcar "Restart playback when source becomes active",
        marcar "Close file when inactive" = **off** (senão o SRT cai ao trocar de cena).
      - "Use hardware decoding when available" = **on** (VideoToolbox no Apple Silicon).
      - Network buffering em 0 (o buffer já é do SRT).
      - Escala/ancoragem da fonte na cena.
- [x] Mic no Mac: **+1613 ms** no Sync Offset do `Mic/Aux`, medido e aplicado
      (`docs/obs-setup.md` §4). O mic chega 1,62 s antes do vídeo — 15 claquetes,
      83% de cobertura, faixa de ±24 ms —, e esse número é a **latência ponta a
      ponta do caminho do vídeo**, que o projeto não tinha medido até aqui.
      Duas armadilhas no caminho: a monitoração do OBS realimenta o microfone
      (a primeira medição deu o sinal invertido) e o bipe acústico precisa ser
      procurado na banda de 1 kHz, senão a cobertura cai para 6%.
- [x] Config de saída para a Twitch no perfil `Untitled` (o único que existe):
      serviço Twitch com a chave, `StreamEncoder = apple_h264` (era `x264`),
      `VBitrate = 6000`, `ABitrate = 160`, AAC. Nada foi transmitido.
      - O **keyframe de 2 s** não é ajustável no modo Simple; ele vem das
        recomendações do serviço, que estão ligadas (`IgnoreRecommended=false`).
        Fica para conferir na primeira transmissão de teste — se não vier, é
        trocar para o modo Advanced, e aí o item volta a abrir.

**Saída:** cena do OBS completa (jogo + mic + overlays), stream de teste privado
na Twitch rodando 15 minutos sem dropped frames.

> **Onde está:** ✅ **FECHADA em 31/08, com folga.** 37 min no ar contra os 15 do
> critério: 134321 quadros, **0 perdidos**, nenhuma reconexão, 6,15–6,20 Mbps e a
> Twitch marcando `EXCELENTE` (`docs/obs-setup.md` §5).
>
> Três achados da rodada, todos registrados:
> 1. O encoder que subiu foi o **x264**, não o `apple_h264` escrito no perfil — o
>    OBS não relê o `basic.ini` em memória. Quem muda config por websocket tem de
>    conferir no log o que de fato subiu.
> 2. O **keyframe de 2 s** se resolveu sozinho (`keyint: 120` a 60 fps), pelas
>    recomendações do serviço.
> 3. O Air **esfriou 3,1 °C durante a transmissão** (33,3 → 30,2 °C, sem um aviso
>    de `CPU_Speed_Limit`). O calor vinha de um `srt-live-transmit` órfão dos meus
>    testes queimando um núcleo havia 1h38 — e os 0 quadros perdidos foram obtidos
>    **com esse núcleo a menos**, então a margem real é maior que a medida.
>
> **Dois itens saíram daqui por não terem critério técnico**, e nenhum bloqueia
> nada: os *overlays* da cena são escolha de produção, e trocar o encoder para o
> `apple_h264` virou tuning — mede-se na Fase 7, agora que se sabe que o x264
> cabe no Air com folga térmica.

---

### Fase 5 — Robustez

Aqui o projeto para de ser "dois comandos" e vira algo que aguenta uma sessão real.

- [x] `supervisor.py`: se o ffmpeg morrer, reiniciar com backoff exponencial e
      teto; logar o motivo. Nunca deixar processo órfão segurando a porta 9000.
      O motivo sai **classificado** a partir do que o próprio ffmpeg disse antes
      de morrer, e a classificação decide se vale reerguer — porta ocupada e
      device de áudio ausente não valem, porque se repetiriam iguais para sempre.
- [x] **Reerguer a captura no `DXGI_ERROR_ACCESS_LOST`** — medido na Fase 2
      (`docs/fase2.md` §8). ⚠️ **A premissa original deste item estava errada:**
      ele dizia "detectar mudança de resolução/refresh", e no caso real o desktop
      **não mudou** de modo (seguiu 1920x1080@60) — quem quebrou foi o jogo saindo
      do compositor ao entrar em fullscreen exclusivo. Vigiar a resolução não
      pegaria isso. O gatilho certo é o próprio erro do ffmpeg
      (`AcquireNextFrame failed: 887a0026`, seguido de `Conversion failed!`), e a
      recuperação é reiniciar o processo: o filtro `ddagrab` não tem opção de
      reinicializar sozinho.
- [x] Logs rotativos em arquivo + `--verbose` (no **arquivo**, não no console —
      o console já recebe tudo do ffmpeg direto, e duplicar seria ruído; a flag
      troca a amostra pelo registro completo do progresso). A primeira linha do
      arquivo é sempre o comando que rodou, e a linha de progresso entra por
      **amostragem** (`[logs] batimento_s`, 30 s) — guardá-la inteira encheria o
      log e a rotação descartaria as linhas de erro, que são as raras e as que
      explicam. Não conseguir escrever o log **avisa e segue**: quem vai jogar não
      quer descobrir que o `send` não sobe porque uma pasta não pôde ser criada.
- [x] `lanstream send --watch`: fica no ar esperando o OBS conectar/reconectar,
      sem precisar reiniciar nada do lado do Windows.
      **A Fase 2 mostrou que metade disso já existe de graça:** o Media Source do
      OBS tem `reconnect_delay_sec = 2` e tenta sozinho a cada 2 s — medido, ele
      agarrou o sender ~22 s antes de alguém pedir (`proximos-testes.md`, regra 1).
      Com o `--watch` do lado do Windows o par passa a se recuperar **sem ação
      humana nenhuma**, e não só sem reiniciar o sender.
      Falta a prova no Windows real; a lógica está verificada com um ffmpeg falso
      (`docs/fase5.md` §1).
- [x] Auto-start opcional no Windows via `lanstream install-autostart`
      (`--dry-run` mostra o que seria escrito, `--remove` desfaz).
      **Atalho na pasta Inicializar, e não Task Scheduler, por um motivo medido:**
      tarefa agendada roda sem console, e sem console o `CTRL_C_EVENT` não tem
      onde chegar — que é exatamente o mecanismo que a Fase 2 mediu para o ffmpeg
      encerrar limpo, escrevendo o trailer e soltando a porta (`fase2.md` §5).
- [x] ~~(Opcional) Anúncio mDNS/Bonjour do sender~~ — **não construído, de
      propósito.** O próprio item já dizia que só valeria se o IP do Windows
      mudasse de fato, e ele não mudou em nenhuma das rodadas; uma reserva de
      DHCP no roteador resolve com zero código e zero peça nova para quebrar.

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
- [ ] ~~Testar 1440p e 120fps~~ — **inviável neste hardware:** o monitor do Windows
      é 1920x1080 @ 60 Hz e o `ddagrab` captura o que a tela tem. 1080p60 é o teto
      físico. Reavaliar só se o monitor mudar.
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
| `ddagrab` não captura o jogo (fullscreen exclusivo / anti-cheat) | 🟢 **Materializou-se em parte, e o fallback resolveu** | **Fase 2 (30/08): jogo 3D moderno capturado em borderless** — RE2 remake, 3 min, 57.1 fps, 14.5–15.2 Mbps, `drop=0`, imagem no OBS do Mac. **Fullscreen exclusivo derruba a captura** com `DXGI_ERROR_ACCESS_LOST` (`docs/fase2.md` §8): o fallback previsto aqui — borderless windowed — virou o modo suportado do projeto. Anti-cheat segue não testado (o RE2 single-player não carrega nenhum). |
| Áudio loopback no Windows exige software de terceiro | 🔴 Confirmado | **Fase 0:** não existe nenhum device de loopback na máquina (`Win32_SoundDevice` só lista Realtek + NVIDIA HDMI). A Fase 3 começa do zero e exige instalar driver + reboot. |
| **Caminho assimétrico: downlink roteador→Mac** | 🔴 Alto | **É o gargalo real (`baseline` §4c).** Mac→Windows faz 93.5 Mbps TCP e 60 Mbps UDP com 0% perda; Windows→Mac faz 68 Mbps TCP e perde 5.5% a 25 Mbps. A única perna não compartilhada é o downlink do AP. Correção provável: **Mac no cabo** (adaptador USB-C) — não o cabo do Windows, que já provou carregar 93.5 Mbps. |
| **A rede não sustentar o bitrate** | 🟡 Médio | **Rebaixado.** O teto de 16 Mbps do `baseline` §4 era artefato da rajada não pacejada do `iperf3 -u`: no mesmo caminho o TCP faz 68 Mbps. A SRT se pacea e tem ARQ. Alvo segue em 15 Mbps até o experimento de buffer de 1.2 s dizer se dá pra subir. |
| **Link Ethernet do Windows a 100 Mbps** | 🟢 Baixo | **Praticamente inocentado (`baseline` §4c).** O link negocia 100M, mas **entrega 93.5 Mbps de TCP no sentido de entrada** e a placa não acusa um único erro ou descarte de saída. Não é ele que limita o stream. Trocar o cabo continua sendo melhoria (subiria pra 1 Gbps), não correção. |
| **`ddagrab` entrega ~57 fps, não 60** | 🟡 Médio | **Fase 0.** Gargalo é a captura, não o encoder (fonte sintética faz 270 fps). Pode ser artefato da Desktop Duplication com tela quase parada — ela só entrega frame quando há mudança. Remedir com jogo real antes de tratar como problema. |
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
