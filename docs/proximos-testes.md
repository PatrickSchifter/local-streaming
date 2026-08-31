# Próximos testes — o que rodar no Windows

Ordem de prioridade. Cada teste diz o comando exato, o que eu faço do lado do Mac,
e **o que o resultado decide** — nenhum teste aqui é "por garantia".

🔴 **A vez é do F3 — o áudio.** O **F2 fechou em 30/08** com os cinco passos, e
com ele a Fase 2 (registro abaixo e em [`docs/fase2.md`](fase2.md)). O F3 começa
com um bloqueio de hardware: esta máquina **não tem device de captura de áudio
nenhum** (`baseline.md` §7), e o primeiro passo custa dois minutos e pode
resolver isso sozinho.

O **F1** era da Fase 1 e **passou em 29/08** — a Fase 1 fechou, registro em
[`docs/fase1.md`](fase1.md). Os T1–T6 são resquícios da Fase 0: ela fechou sem
eles, e cada um diz no título se ainda vale a pena.

Contexto: `docs/baseline.md` §4e. O caminho Windows→Mac entrega ~17 Mbps limpos, o
buffer alto troca corrupção por queda de framerate, e falta achar a configuração
que roda a 60 fps dentro desse teto.

---

## ⚠️ Regras que valem para todos os testes

1. **Reinicie o sender entre cada rodada.** O ffmpeg em modo SRT `listener` trata a
   desconexão do caller como erro fatal e morre com
   `Error submitting a packet to the muxer: I/O error`. Cada execução atende **uma
   única conexão** (§4e). Se o log parar em `Media path` sem chegar em
   `SRT source connected`, é isso — o sender já morreu.

   > 🟡 **Corolário do F2.3 (30/08): o OBS conecta sozinho, sem ninguém pedir.**
   > O Media Source tem `reconnect_delay_sec = 2` e `close_when_inactive = false`,
   > então ele tenta a cada 2 segundos por conta própria. Medido duas vezes: no
   > flapping `PLAYING`/`ENDED` da tentativa fracassada, e na segunda rodada, em
   > que o cursor já estava em **22.3 s de mídia** quando fui olhar — o OBS tinha
   > agarrado o sender ~22 s antes, sem eu disparar nada.
   >
   > **Consequência prática: não existe "avise que eu conecto".** Quem sobe o
   > sender não precisa esperar ninguém; o aviso só serve para começar a medir.
   >
   > ❌ **Uma correção, porque a versão anterior deste box errava a causa.** Eu
   > tinha escrito que o OBS havia *consumido* a conexão única da primeira
   > tentativa. Não foi isso: o log do Windows mostra o sender morrendo sozinho em
   > **4.28 s com `DXGI_ERROR_ACCESS_LOST`**, o fullscreen exclusivo do §F2.3-bis
   > — provavelmente antes de o OBS sequer tentar. Eu inferi uma causa no emissor
   > a partir de um sintoma no receptor (`ENDED`, cursor parado), quando o log do
   > emissor tinha a resposta. **A regra que fica: quando as duas pontas discordam,
   > vale a que tem o log, não a que tem o sintoma.**
2. **uTorrent e qualquer download/upload pesado fechados.** Não pausados: fechados.
3. **`git pull` nas duas máquinas antes de começar** — o `win-test-video.ps1` ganhou
   o parâmetro `-Codec`, que os testes abaixo usam.
4. **Me avise quando o sender estiver escutando.** Eu conecto do Mac, meço e colo os
   números. Sem o lado do receptor, metade do experimento não existe — foi o que
   aconteceu no §4d.
5. **`fps` é a métrica de freio — `speed` não é.** Numa fonte ao vivo o `ddagrab`
   carimba timestamp em tempo real, então `speed` = tempo de mídia ÷ relógio de
   parede fica ~1.0 mesmo perdendo frame (medido: 52 fps *com* speed 0.995x).
   `speed` só cai quando a **captura trava**, que é coisa mais grave — foi o que o
   §4d viu a 0.942x. Não use os dois como se fossem o mesmo eixo (§4f).
6. **`fps=` do ffmpeg é média acumulada — não taxa instantânea.** Ele é
   `frame ÷ elapsed` desde o início, então sobe sozinho durante a corrida e
   **corridas curtas subestimam o fps**. Para a taxa real, pegue duas amostras e
   faça `Δframe ÷ Δt`. Nunca compare fps de corridas de duração diferente (§4h).
   Referência medida com jogo real: **54–58 fps instantâneos, média 56.2**.
7. **Tela em movimento durante a medição.** Com o desktop parado o `hevc_nvenc` em
   CBR entrega ~1.7 Mbps e a rede nunca é estressada — `-b:v` é teto, não piso.
   Rodada com tela parada não mede nada e o `0 drops` dela é falso positivo (§4f).

---

## F3 — áudio do jogo 🟡 **F3.1–F3.3 passaram em 31/08; falta o número do F3.4**

> 📄 **Quem está sentado no Windows quer o [`windows.md`](windows.md)**, que é o
> mesmo protocolo sem o registro: comandos na ordem, sintoma → causa, e as regras
> que já custaram tempo. Este documento aqui guarda o *porquê* e o resultado de
> cada rodada.

> **O bloqueio do device caiu.** O device é o **`virtual-audio-capturer`**, já
> escrito no `lanstream.toml` do Windows, medido com o GTA tocando (mean −29,0 dB)
> e confirmado pelo ouvido no OBS do Mac. A Mixagem estéreo do Realtek foi
> testada e **não serve nesta máquina**: a saída é HDMI e o Stereo Mix é da placa
> onboard — o porquê está em `docs/fase3.md` §1.
>
> **O que sobrou é do Mac, e é uma coisa só: a mediana do F3.4 sobre uma
> gravação.** O passo "Do lado do Mac" logo abaixo tem os comandos prontos.
>
> ⚠️ **Não mexa no `[audio] offset_ms` antes de medir.** No F3.3 o áudio parecia
> 2–3 s atrasado; o sender foi medido e está alinhado em **21 ms**, antes e depois
> do SRT (`docs/fase3.md` §8). O atraso nasce do lado do Mac, e `offset_ms`
> corrige o sender — escrever 2500 ali quebraria o que já está certo.

Tudo o que não depende da máquina do Windows já está feito e medido
(`docs/fase3.md`): o comando com as duas trilhas foi montado, rodado num ffmpeg
de verdade e verificado com `ffprobe`, e o sinal do `-itsoffset` foi medido em
vez de presumido.

### Do lado do Mac — o que falta, em ordem

Nada precisa ser instalado nem gerado aqui: a claquete nasce no Windows (ela é
`.gitignore`, cada máquina gera a sua) e a medição roda sobre a gravação do OBS.

**1. Antes de tudo, o log do OBS.** No F3.3 o áudio soou 2–3 s atrasado e a causa
não foi encontrada — só foi provado que não é o sender. Procure em
`Ajuda > Arquivos de Log > Mostrar Logs`:

```
adding N ms of audio buffering, total audio buffering is now N ms
```

O OBS sobe esse buffer sozinho quando os timestamps chegam trêmulos, e ele é
*sticky*: só zera reiniciando a fonte. Confira junto o `Sync Offset` da fonte em
**Propriedades de Áudio Avançadas** (tem que ser 0) e o **Network Buffering** do
Media Source. Se o relato de "ficou sincronizado" veio do **monitoramento**, vale
lembrar que o caminho de monitoração tem latência própria e **não** entra no
`.mkv` — o que decide é a medição do passo 3.

**2. Gravar.** Com o Windows tocando o `claquete.mp4` em tela cheia e o `send` no
ar, `OBS → Iniciar Gravação`. **Comece com 2 minutos**: a mediana aparece igual
num arquivo curto, e se algo estiver errado o prejuízo é 2 min em vez de 20. Os
20 min continuam sendo o critério de saída, mas eles medem **deriva**, não offset
— vale rodá-los depois que a mediana curta vier boa.

**3. Medir:**

```bash
python scripts/av-sync.py medir ~/Movies/<arquivo>.mkv --offset-atual 0
```

`--offset-atual 0` porque o `lanstream.toml` do Windows está com `offset_ms = 0` —
o script não lê o config da outra máquina, então esse número é premissa e precisa
bater com o que está lá.

**4. O que o resultado decide** está na tabela do F3.4, mais abaixo. Compare com o
viés de **+12 ms** do próprio arquivo de claquete, não com zero.

> **A restrição que ordena as tentativas:** o áudio precisa continuar saindo pela
> caixa de som — quem está jogando está sentado nela. Uma captura que emudece o
> jogo para o jogador não serve, por mais limpa que seja. É por isso que a ordem
> aqui **não** é a do PLANO original (ver `docs/fase3.md` §1).

### A sequência inteira, para conferir depois

Os comandos do Windows, na ordem. Cada um está explicado no passo correspondente
— esta lista é para saber onde você está, não para colar às cegas.

```powershell
cd C:\Users\schif\Projetos\local-streaming
git pull
uv pip install -e ".[dev]"                          # há um módulo novo (audio.py)

lanstream doctor --audio                            # F3.1 — qual device existe?
#   ... colar o nome em [audio] device e ligar enabled = true ...
lanstream doctor                                    # F3.2 — o device confere?
lanstream send --dry-run                            # F3.2 — o comando saiu certo?

lanstream send                                      # F3.3 — sai som no OBS?
lanstream send --no-audio                           # F3.3 — só se o de cima falhar

python scripts\av-sync.py claquete claquete.mp4 --segundos 1260   # F3.4
lanstream send                                      # F3.4 — com a claquete tocando
lanstream send                                      # F3.5 — com o jogo, borderless
```

O que **eu** faço daqui: conectar o OBS (ele reconecta sozinho), gravar 20 min no
F3.4, e rodar a medição na gravação. O F3.1 e o F3.2 não precisam de mim.

### F3.1 — o device: comece pelo que é de graça ⏱️ 2 min

O `Win32_SoundDevice` que o baseline consultou lista placas, não entradas — e o
Windows esconde a Mixagem estéreo **desabilitada**, não ausente. Então "esta
máquina não tem loopback" ainda pode ser falso. Antes de instalar qualquer driver:

1. `Win + R` → `mmsys.cpl` → aba **Gravação**
2. botão direito na lista → **Mostrar dispositivos desativados**
3. se aparecer **Mixagem estéreo** (ou *Stereo Mix*): botão direito → **Ativar**

```powershell
lanstream doctor --audio
```

**O que decide:**
- **Apareceu um device `loopback`** → copie o nome exato, vá para o F3.2. A fase
  ficou de graça.
- **Só apareceu microfone, ou nada** → é instalação de driver, com reboot. Ordem
  em `docs/fase3.md` §1: VB-CABLE (lembrando de marcar **Ouvir este dispositivo**
  em `Gravação > CABLE Output > Propriedades > Ouvir`, senão o jogo emudece para
  quem joga), e VoiceMeeter se a latência do "Ouvir" atrapalhar. Depois de
  instalar, volte a este passo.

> ⚠️ **O `doctor --audio` classifica pelo NOME**, e isso é palpite: `loopback`,
> `microfone` ou `desconhecido`. Quem confirma é o ouvido, no F3.3.

### F3.2 — ligar o áudio na config ⏱️ 1 min

```toml
[audio]
enabled = true
device = "virtual-audio-capturer"   # o nome EXATO do F3.1 — este é o desta máquina
```

```powershell
lanstream doctor          # agora com as checagens de áudio
lanstream send --dry-run
```

**Esperado:** `[ OK ] device de áudio: "..." (loopback)` e, no comando, o bloco
`-f dshow -audio_buffer_size 50 -thread_queue_size 1024 -i "audio=..."` com
`-map [v] -map 0:a` e `-c:a aac -b:a 160k -ar 48000 -ac 2`.

**O que decide:** um nome que erra por caixa ou acento é FALHA aqui, com o nome
certo impresso para copiar — o dshow abre o device pelo nome literal. Corrigir
custa uma linha; descobrir isso com o `send` no ar custa a rodada.

### F3.3 — o áudio existe? ⏱️ 3 min, precisa do Mac

Toque **qualquer coisa** no Windows (YouTube serve) e:

```powershell
lanstream send
```

No Mac, o Media Source já conectado (ele reconecta sozinho a cada 2 s — ver as
regras acima). **O que decide:**

- **Sai som no OBS** → siga para o F3.4.
- **Sai som, mas é o microfone / o ambiente do quarto** → o device é de captura,
  não de loopback. Volte ao F3.1.
- **Não sai som nenhum, e o vídeo continua bom** → o device não está entregando.
  Confira o nível dele em `mmsys.cpl > Gravação` enquanto o áudio toca: se a
  barrinha não mexe, o problema é o Windows, não o ffmpeg.
- **O `send` nem sobe** → rode `lanstream send --no-audio`. Se com isso funciona,
  o problema é o device (o comando sem áudio é **byte a byte** o da Fase 2). Se
  não funciona nem assim, é regressão do vídeo, e aí o áudio não tem nada com isso.

### F3.4 — o número: A/V sync medido ⏱️ 10 min, precisa do Mac

Aqui entra a claquete: tela preta que pisca branco por 100 ms a cada 5 s, com um
bipe de 1 kHz nos mesmos 100 ms. **Ela nasce aí mesmo** — nada para copiar entre
as máquinas, e o arquivo sai do mesmo código que faz a medição:

```powershell
python scripts\av-sync.py claquete claquete.mp4 --segundos 1260
```

> Usa só o ffmpeg do PATH, o mesmo que o `doctor` já achou. 21 minutos de vídeo,
> quase tudo preto: o arquivo dá poucos MB.

1. **Windows:** toque o `claquete.mp4` em **tela cheia** (qualquer player), com o
   som saindo pelo device que o F3.1 escolheu — se você habilitou a Mixagem
   estéreo, é a saída normal. Rode `lanstream send`.

   > ⚠️ **Nada mais pode estar tocando.** O `virtual-audio-capturer` captura o
   > endpoint padrão inteiro, não o player: jogo aberto, música, aba de navegador
   > e som de notificação entram junto. Na rodada de 31/08 às 12:16 foi isso que
   > aconteceu — a gravação veio com conteúdo largo e contínuo de 0 a 12 kHz e
   > **sem o tom de 1 kHz da claquete em lugar nenhum** (medido na banda: −79 dB
   > no instante do flash contra −85 a −61 dB entre eles, ou seja, indistinguível
   > do ruído). O vídeo estava perfeito, 26 flashes sem faltar um.
   >
   > Antes de gravar, confira as três: **(a)** nada além do player fazendo som —
   > feche o jogo; **(b)** o player está mandando o áudio para o **dispositivo
   > padrão** do Windows, não para um específico; **(c)** o volume está audível.
   > E que o arquivo tem trilha de áudio: `ffprobe claquete.mp4` precisa listar
   > um stream `aac`.
2. **Mac:** com o Media Source pegando a imagem, **OBS → Iniciar Gravação**.
   Deixe correr **20 minutos** — é o critério de saída da fase, e é o tempo que
   uma deriva precisa para aparecer.
3. **Mac:** parar a gravação, parar o `send` com Ctrl+C, e medir:

```bash
python scripts/av-sync.py medir ~/Movies/2026-08-31\ 20-00-00.mkv --offset-atual 0
```

**O que decide:**

| Resultado | Significa | Ação |
|---|---|---|
| mediana < 40 ms e deriva ~0 | sincronizado dentro do piso do método | **fase fechada**, não mexa no offset |
| mediana estável, deriva ~0 | offset constante | cole a linha `[audio] offset_ms = N` que o script imprime, e refaça o F3.4 para confirmar |
| deriva medida acima do ruído (>40 ms entre as metades) | dois relógios correndo diferente | `-itsoffset` **não** resolve; é `aresample=async=1`, e vira item da Fase 7 com esta medição junto |
| nenhum par encontrado | leia a mensagem: `bipes sem flash` é a cena (fonte pequena ou overlay claro), `flashes sem bipe` é o F3.3 falhando | o script já tenta os dois limiares sozinho; se insistir, `--pic-th 0.80` |

> **Compare com o viés, não com zero.** O próprio arquivo de claquete mede `+12 ms`
> porque `blackdetect` só responde no quadro seguinte e `silencedetect` decide por
> janelas de ~21 ms. O que interessa é quanto a gravação se afasta desse número.
>
> **E o que 20 minutos conseguem decidir sobre deriva:** o piso de ruído de 40 ms
> sobre uma separação de 10 min entre as metades dá **~240 ms/hora** de resolução.
> Uma deriva menor que isso existe mas não aparece nesta gravação — e ela custaria
> menos de 80 ms numa sessão de 20 min, que é o limite do que se percebe. Se a
> sessão real for de horas, refaça a medição com uma gravação longa; o script
> imprime a resolução da janela que ele teve.

### F3.5 — a rodada real ⏱️ o resto da sessão

Jogo em **borderless** (a restrição do §F2.3-bis vale igual aqui), áudio ligado,
20 minutos. **O que decide:** fps e bitrate não podem piorar em relação ao F2.3
(57.1 fps instantâneos, 14.5–15.2 Mbps, `drop=0`) — o AAC custa 160 kbps e não
deveria mexer em nada, mas é o encoder de vídeo dividindo máquina com uma segunda
captura, e isso se mede em vez de se supor.

### Tabela para preencher

| Passo | Resultado |
|---|---|
| F3.1 device encontrado | ✅ `virtual-audio-capturer` — mean −29,0 dB / max −11,4 dB, 48 kHz estéreo |
| F3.2 doctor OK | ✅ tudo OK, zero AVISO |
| F3.3 som no OBS | ✅ sai som do jogo; as duas trilhas no mux |
| F3.4 mediana / deriva | 🔴 **falta** — é o único item aberto da fase |
| F3.5 fps / bitrate / drops | 🟡 parcial: 60 fps, speed 0,995–0,997x, 15,6 Mbps *com* áudio; faltam os 20 min |

---

## F2 — `lanstream send` no Windows ✅ **os cinco passaram — Fase 2 fechada em 30/08**

O código está escrito e verificado no que não depende do Windows (`docs/fase2.md`
§5). Três coisas só esta máquina responde: o `ddagrab`, o NVENC, e o **Ctrl+C do
console do Windows** — o teste daqui foi um SIGINT em POSIX, e o `CTRL_C_EVENT`
percorre outro caminho.

> **Rodado em 30/08, e as três responderam.** O NVENC é escolhido e monta o
> comando da Fase 0 (F2.1/F2.2); o `CTRL_C_EVENT` do Windows encerra o ffmpeg
> limpo, sem órfão, sem `terminate` (F2.4/F2.5); e o `ddagrab` entregou o jogo com
> o OBS do Mac do outro lado (F2.3) — **em borderless**. Em fullscreen exclusivo a
> captura morre com `DXGI_ERROR_ACCESS_LOST`, que é o achado do §F2.3-bis e a
> única restrição nova que a fase produziu.

São cinco passos. Os quatro primeiros levam ~2 minutos e **não precisam de mim do
outro lado**; só o F2.3 precisa do OBS aberto no Mac.

### Antes: atualizar

```powershell
cd C:\Users\schif\Projetos\local-streaming
git pull
uv pip install -e ".[dev]"    # há módulos novos (encoders.py, sender.py)
```

> O `lanstream.toml` daí **não precisa mudar por causa do `preset`**. Se ele tem
> `preset = "p5"`, continua válido — `p5` é um preset da família NVENC. A
> diferença é que agora a chave pode ficar vazia e dá no mesmo (`docs/fase2.md` §2).
>
> ❌ **Mas precisou mudar por outro motivo, e a instrução acima está incompleta.**
> O `lanstream.toml` do Windows ainda tinha `host = "192.168.0.21"` (o Mac), que
> era a instrução da Fase 0/1. Com a separação `host`/`peer` do commit 010d763
> isso virou **FALHA** — e a FALHA é o comportamento correto, é para isso que a
> checagem existe. O arquivo daqui agora é:
>
> ```toml
> [network]
> host = "192.168.0.12"   # esta máquina, o sender
> peer = "192.168.0.21"   # o Mac
> ```
>
> Quem tinha o `host` antigo precisa fazer essa troca **antes** do F2.1, senão o
> passo falha por config velha e não por defeito no código.

### F2.1 — o doctor ganhou uma checagem

```powershell
lanstream doctor
```

Esperado: **onze** checagens, todas OK, código 0 — duas a mais que as nove do
registro da Fase 1. Uma veio da separação `host`/`peer` (`host do sender`, commit
010d763, ainda da Fase 1) e a outra é a da Fase 2: `preset`, que deve dizer
`preset: -preset p5`.

**Se falhar:** cole a saída. Uma FALHA aqui invalida os passos seguintes.

> ✅ **Passou em 30/08 — 11 checagens, 11 OK, código 0.** ffmpeg 8.1
> (`full_build-www.gyan.dev`), `hevc_nvenc` escolhido, `preset: -preset p5` com a
> nota `(default da família — [video] preset está vazio)`, `ddagrab` e SRT
> presentes, regra de firewall viva, IP ainda **192.168.0.12**, porta 9000 livre,
> `host do sender: 192.168.0.12 — é esta máquina, como deve ser` e
> `alcance até 192.168.0.21: responde ao ping`.
>
> ⚠️ **A décima primeira checagem depende do `peer`.** Sem `[network] peer`
> preenchido saem **dez** — a linha de alcance simplesmente não existe, e o doctor
> imprime a dica `(opcional: [network] peer = IP do Mac ...)` no lugar. Só dá onze
> com o `peer` no toml. A primeira execução, com o `host` velho, deu dez linhas e
> FALHA no `host do sender`; ver o achado acima.

### F2.2 — o comando montado é o mesmo da Fase 0? (o passo mais barato)

```powershell
lanstream send --dry-run
```

Compare a linha impressa com a do `scripts/win-test-video.ps1`. A **única**
diferença esperada é o `-nostdin`. Confira nominalmente:

- [ ] `-init_hw_device d3d11va`
- [ ] `-filter_complex ddagrab=0:framerate=60` — sem nada depois do `ddagrab`
- [ ] `-c:v hevc_nvenc -preset p5 -tune hq -rc cbr`
- [ ] `-b:v 15M -maxrate 15M -bufsize 15M -g 120 -bf 0`
- [ ] `-f mpegts "srt://0.0.0.0:9000?mode=listener&latency=1200000"`

**O que o resultado decide:** se algo aqui divergir, o problema é meu, do lado do
Mac, e não vale queimar uma sessão de teste. Cole a linha e eu conserto.

> ✅ **Passou em 30/08 — os cinco itens conferem, nada divergiu.** A linha impressa
> aqui, na íntegra:
>
> ```
> C:\Users\schif\AppData\Local\Microsoft\WinGet\Links\ffmpeg.EXE -hide_banner -loglevel info -stats -nostdin -init_hw_device d3d11va -filter_complex ddagrab=0:framerate=60 -c:v hevc_nvenc -preset p5 -tune hq -rc cbr -b:v 15M -maxrate 15M -bufsize 15M -g 120 -bf 0 -f mpegts "srt://0.0.0.0:9000?mode=listener&latency=1200000"
> ```
>
> Contra o `win-test-video.ps1` a diferença é o `-nostdin`, como previsto — e o
> argv[0], que aqui é o caminho absoluto resolvido pelo doctor em vez do `ffmpeg`
> do PATH que o script da Fase 0 usava. Sem espaço no caminho, então sem aspas e
> sem o `&` do `shell_line`.

### F2.3 — a rodada real (esta precisa do Mac)

Tela **em movimento** (regra 7), uTorrent fechado (regra 2). Me avise quando
estiver escutando (regra 4) — eu conecto o OBS do Mac.

```powershell
lanstream send
```

O que anotar:

| O quê | Onde aparece | Referência da Fase 0 |
|---|---|---|
| Encoder escolhido | primeira linha ciano do `send` | `hevc_nvenc` |
| fps **instantâneo** | `Δframe ÷ Δt` entre duas amostras — **não** o `fps=` (regra 6) | 54–58, média 56.2 |
| `speed` | linha de progresso | ~1.000x |
| Imagem no OBS | eu confirmo daqui | — |

> ⚠️ **O sender atende UMA conexão e morre** (regra 1). Se eu desconectar o OBS,
> ele sai com `Error submitting a packet to the muxer: I/O error`. **Isso não é
> bug da Fase 2** — o `--watch` que resolve isso é da Fase 5. Reinicie e siga.

> ⚠️ **O `drop=1` das rodadas curtas de 30/08 não é novidade** — está explicado no
> veredito no fim desta seção. Com receptor e tela em movimento, a referência da
> Fase 0 é `drop=0` em 10 minutos.

**O lado do Mac já está pronto** (30/08): `lanstream.toml` com
`host = "192.168.0.12"`, doctor todo verde, e o Windows respondendo por ARP. A
URL que eu vou colar no Media Source do OBS é

```
srt://192.168.0.12:9000?mode=caller&latency=1200000
```

com `Input Format = mpegts` e "Local File" desmarcado — a receita da Fase 0
(`baseline` §5). Se o IP do Windows tiver mudado desde então, o F2.1 acusa antes
deste passo.


> ## ✅ Passou em 30/08 — na segunda tentativa, e a primeira ensinou mais que a segunda
>
> **Jogo:** Resident Evil 2 (remake, RE Engine) — o jogo 3D moderno que o T3
> deixou em aberto. **Modo: borderless, 1920x1080.** Ver o §F2.3-bis logo abaixo
> para o motivo de não ser fullscreen exclusivo.
>
> | O quê | Medido | Referência |
> |---|---|---|
> | Encoder | `hevc_nvenc` | `hevc_nvenc` |
> | fps **instantâneo** (janela 117.6s→177.4s) | **57.1** | 54–58, média 56.2 |
> | faixa de fps ao longo da corrida | 55.9–57.7, sem tendência de queda | — |
> | bitrate **instantâneo** | **14.5–15.2 Mbps sustentados** | T1 deu 1.67, T3 deu 9.6 |
> | `speed` | 0.999 → 1.000x | ~1.000x |
> | `drop` / `dup` | **0 / 0** em 10.056 frames | 0 |
> | duração | 177.4 s de mídia, sem erro no log | — |
> | Ctrl+C no fim | 0.60 s, sem órfão, porta livre | 0.11 s (Mac) |
> | Imagem no OBS do Mac | ✅ **confirmada** | — |
>
> **Esta é a primeira rodada do projeto que de fato estressa o teto de ~17 Mbps
> do §4e.** O T1 pediu 15M e entregou 1.67 (tela parada, §4f) e o T3 entregou 9.6
> (jogo 4:3 pré-renderizado de 30 fps). Com o RE2 a 14.5–15.2 Mbps sustentados o
> `-b:v 15M` finalmente virou piso e teto ao mesmo tempo — e o sender não freou.
>
> ✅ **Dívida quitada no mesmo dia: os contadores do lado do Mac.** Foram
> coletados durante esta rodada, via `obs-websocket` (`GetStats` +
> `GetMediaInputStatus`), e confirmam o lado do sender em vez de contradizê-lo —
> o buraco do §4d (sender feliz, receptor sofrendo) **não se repetiu**:
>
> | O quê | Medido no Mac | Como |
> |---|---|---|
> | Estado da fonte | `PLAYING` contínuo, sem uma queda | `GetMediaInputStatus` a cada 10 s |
> | **Mídia / relógio de parede** | **0.9997** numa janela de 60 s | `Δcursor ÷ Δrelógio` |
> | Frames descartados pelo OBS | **0** (`renderSkippedFrames` travado em 11) | `GetStats` |
> | Render do OBS | 60.00 fps | `ΔrenderTotalFrames ÷ Δt` |
> | CPU do OBS | 10.7–11.1% | `GetStats` |
> | Memória | 280–339 MB | `GetStats` |
> | Imagem | ✅ confirmada **por captura**, não a olho | `GetSourceScreenshot` |
> | Movimento | ✅ duas capturas com 60 s de intervalo diferem | comparação de bytes |
>
> A captura está em [`docs/img/fase2-f23-obs.png`](img/fase2-f23-obs.png): o salão
> do RPD, cena escura, **sem macrobloco visível** — que é onde 15 Mbps HEVC
> denunciaria primeiro.
>
> **As duas pontas fecham no fim da corrida.** O sender registrou 177.4 s de mídia
> e Ctrl+C em 0.60 s; a última amostra boa do Mac pegou o cursor em **168.5 s** e a
> seguinte já achou `ENDED`. A janela de 10 s entre as amostras explica a
> diferença. O encerramento limpo do Windows aparece do lado de cá como o que
> deveria ser: o stream simplesmente acaba.
>
> ⚠️ **O que continua não coletado, e por quê:** `RCV-DROPPED` e os demais
> contadores do **libsrt**. O obs-websocket não os expõe — o OBS não publica as
> estatísticas internas do SRT. Quem as tem é o `srt-live-transmit`, ou seja o
> `receive --preview` da **Fase 4**. Enquanto ele não existe, "0 frame descartado
> pelo OBS + mídia/relógio 0.9997" é a melhor prova disponível de que nada se
> perdeu no caminho, e é uma prova forte: perda de pacote apareceria como cursor
> atrasando em relação ao relógio.
>
> <details>
> <summary><b>Série temporal completa da rodada</b> — amostra a cada 10 s, fps e bitrate instantâneos</summary>
>
> ```
> [   10s] midia=  7.21s  fps_inst= 57.7   2.48 Mbps  speed=0.992x  drop=0
> [   20s] midia= 17.01s  fps_inst= 56.5  13.00 Mbps  speed=0.996x  drop=0
> [   30s] midia= 27.31s  fps_inst= 56.5  14.34 Mbps  speed=0.998x  drop=0
> [   40s] midia= 37.11s  fps_inst= 55.9  14.37 Mbps  speed=0.999x  drop=0
> [   50s] midia= 46.91s  fps_inst= 56.1  14.67 Mbps  speed=0.999x  drop=0
> [   60s] midia= 57.22s  fps_inst= 56.6  14.36 Mbps  speed=0.999x  drop=0
> [   70s] midia= 67.02s  fps_inst= 56.3  14.53 Mbps  speed=0.999x  drop=0
> [   80s] midia= 77.33s  fps_inst= 56.4  14.49 Mbps  speed=0.999x  drop=0
> [   90s] midia= 87.13s  fps_inst= 56.5  14.47 Mbps  speed=0.999x  drop=0
> [  100s] midia= 96.95s  fps_inst= 57.0  14.68 Mbps  speed=0.999x  drop=0
> [  110s] midia=107.26s  fps_inst= 56.5  14.66 Mbps  speed=0.999x  drop=0
> [  120s] midia=117.06s  fps_inst= 56.6  14.32 Mbps  speed=0.999x  drop=0
> [  130s] midia=127.36s  fps_inst= 56.8  14.56 Mbps  speed=1.0x    drop=0
> [  140s] midia=137.15s  fps_inst= 57.2  14.79 Mbps  speed=1.0x    drop=0
> [  150s] midia=146.96s  fps_inst= 56.4  14.47 Mbps  speed=1.0x    drop=0
> [  160s] midia=157.27s  fps_inst= 57.1  14.72 Mbps  speed=1.0x    drop=0
> [  170s] midia=167.07s  fps_inst= 57.4  14.62 Mbps  speed=1.0x    drop=0
> [  180s] midia=177.38s  fps_inst= 57.5  15.20 Mbps  speed=1.0x    drop=0
> ```
>
> A primeira amostra (2.48 Mbps) é o intervalo antes de o jogo estar desenhando —
> a partir dos 20 s o bitrate estabiliza em 14.3–15.2 e **não sobe nem desce** ao
> longo dos 3 minutos. O `speed` sobe de 0.992x para 1.000x e fica: é o transiente
> de início, o mesmo padrão do §4h. Nenhuma amostra abaixo de 55.9 fps.
>
> Cada linha é `Δframe ÷ Δelapsed` entre amostras consecutivas do próprio ffmpeg —
> não o `fps=` dele, que é média acumulada (regra 6).
>
> </details>
>
> 🟢 **A ressalva do uTorrent se resolveu com número.** Ele ficou aberto,
> limitado a 25 KB/s de upload (a regra 2 pede fechado). Contadores da interface
> no período dos testes: **346.2 MB enviados** contra **326.9 MB do próprio
> stream**, e 8.4 MB recebidos. Sobram ~19 MB para a rodada que falhou, o
> overhead de TS/SRT e o torrent — ou seja, terceiros na casa de **0.2 Mbps
> contra 14.7 Mbps do stream**. Não contaminou a medição.

### F2.3-bis — fullscreen exclusivo derruba a captura ❌ **achado novo, é o mais importante do dia**

A **primeira** tentativa do F2.3 falhou, e não por rede: o sender morreu sozinho
4.28 s depois de subir, no instante exato em que o RE2 entrou em fullscreen
exclusivo. O OBS do Mac nunca teve o que receber porque não havia mais sender.

```
[Parsed_ddagrab_0] AcquireNextFrame failed: 887a0026
[Parsed_ddagrab_0] EOF timestamp not reliable
[fc#0] Error requesting a frame from the filtergraph: Generic error in an external library
[out#0/mpegts] video:2063KiB ... muxing overhead: 4.393630%
Conversion failed!
```

`0x887A0026` é **`DXGI_ERROR_ACCESS_LOST`**. Em fullscreen exclusivo o jogo toma
o display para si e sai do compositor (DWM); a Desktop Duplication daquele
monitor deixa de existir, e o `ddagrab` trata isso como fatal.

O que foi descartado como causa, para o achado não virar folclore:

| Hipótese | Verificado |
|---|---|
| O jogo trocou a resolução/refresh | ❌ desktop seguiu **1920x1080@60** durante e depois (`Win32_VideoController`) |
| O `ddagrab` captura janela e perdeu a janela | ❌ ele duplica o **monitor inteiro**; não existe captura de janela aqui |
| Dá para pedir reinicialização ao filtro | ❌ `ffmpeg -h filter=ddagrab`: só `output_idx`, `draw_mouse`, `framerate`, `video_size`, `offset_x/y`, `output_fmt`, `allow_fallback`, `force_fmt`, `dup_frames`. Nada de recuperar acesso |
| Foi o console do sender roubando o foco | 🟡 provável agravante — a rodada 2 subiu com `CREATE_NO_WINDOW` justamente por isso |

**Em borderless o problema não existe:** o jogo volta a desenhar através do DWM,
o `ddagrab` pega a tela inteira, e a rodada de 3 minutos acima passou sem um
único erro. O alt-tab também deixa de derrubar a captura — o que importa na
prática, porque em exclusivo **qualquer** troca de foco reproduz o mesmo
`ACCESS_LOST`.

**O que isto decide:** borderless é o modo suportado pelo projeto, e isso é uma
restrição documentada — exatamente a saída que o T3 previa ("se só borderless
funcionar, vira restrição documentada"). Não é o Plano B do §6 do PLANO: a
captura de jogo 3D moderno **funciona**, só não no modo exclusivo.

**O que isto NÃO decide, para não superestimar o achado:** não foi testado subir
o sender com o jogo **já** em fullscreen exclusivo. O que está medido é que a
*transição* para exclusivo mata uma captura em andamento. É possível que a DDA
consiga duplicar um exclusivo que já estava lá — não sei, e não vou escrever que
sei.

**Consequência para a Fase 5:** o `--watch` deixa de ser só conforto para
reconexão do OBS. Um supervisor que reergue o ffmpeg cobre também o `ACCESS_LOST`
— que é o modo de falha que aparece sozinho, sem ninguém desconectar nada.


### F2.4 — Ctrl+C: o que só o Windows responde 🔴

Este é o passo que existe por causa de uma lacuna conhecida, não por
desencargo. Com o `send` rodando (com ou sem o OBS conectado), aperte **Ctrl+C**
e observe:

- [ ] Aparece `encerrando o ffmpeg (fechando o mux e a porta SRT)...`
- [ ] Volta ao prompt em **~1 s** (aqui foram 0.11 s)
- [ ] **Não** aparece `o ffmpeg não saiu em 5s — mandando terminate`

Se o `terminate` aparecer, o `CTRL_C_EVENT` **não** está chegando no ffmpeg, e a
correção é minha (provavelmente um `CREATE_NEW_PROCESS_GROUP` implícito do
Python no Windows). Me diga — é exatamente o que este passo existe para descobrir.

Logo depois, no mesmo terminal:

```powershell
Get-Process ffmpeg -ErrorAction SilentlyContinue   # esperado: nada
Get-NetUDPEndpoint -LocalPort 9000 -ErrorAction SilentlyContinue   # esperado: nada
```

> ✅ **Passou em 30/08 — o `CTRL_C_EVENT` do Windows chega no ffmpeg.** Três
> rodadas, saída em **0.67 s, 0.27 s e 0.36 s**, código 0 nas três. Em todas:
>
> - `encerrando o ffmpeg (fechando o mux e a porta SRT)...` apareceu;
> - `Exiting normally, received signal 2.` apareceu **depois** dele — ou seja, o
>   ffmpeg tratou o sinal e ainda escreveu o trailer (`muxing overhead: 10.74%`,
>   `Lsize=531KiB`), não morreu no meio;
> - `o ffmpeg não saiu em 5s — mandando terminate` **não** apareceu;
> - `Get-Process ffmpeg`: nada. `Get-NetUDPEndpoint -LocalPort 9000`: nada.
>
> Ou seja: não é preciso mexer em `CREATE_NEW_PROCESS_GROUP`. A herança de grupo
> descrita em `fase2.md` §4 é a decisão certa também no Windows real, e não só no
> SIGINT do POSIX. **A lacuna que este passo existia para descobrir não existe.**
>
> 📎 **Como o Ctrl+C foi disparado, para ser honesto sobre o método:** não foi um
> dedo na tecla. O `send` foi lançado num console próprio (`CREATE_NEW_CONSOLE`)
> com a saída num arquivo, e um harness se anexou àquele console
> (`AttachConsole`) e chamou `GenerateConsoleCtrlEvent(CTRL_C_EVENT, 0)` — o mesmo
> evento que o driver do console gera quando a tecla é apertada, entregue ao grupo
> inteiro do console: o python do `lanstream` **e** o ffmpeg que ele herdou. É o
> caminho do `CTRL_C_EVENT` de verdade, que é exatamente o que o SIGINT do POSIX
> não exercitava. O harness está fora do repositório; dá para commitá-lo se você
> quiser repetir isso sem depender de alguém apertando tecla.

### F2.5 — rodar duas vezes seguidas (a prova de que não sobrou órfão)

É o teste que realmente vale, e custa 20 segundos:

```powershell
lanstream send      # Ctrl+C depois de uns 5 s
lanstream send      # tem que subir na hora
```

Se a segunda subir sem `Address already in use` / `bind failed`, a promessa
"encerra sem deixar ffmpeg segurando a porta 9000" está cumprida **no SO que
importa**. Se não subir, o F2.4 mentiu e é lá que está o defeito.

> ✅ **Passou em 30/08.** Duas rodadas encostadas uma na outra (~1 s entre o fim de
> uma e o começo da outra). A segunda subiu na hora, com o mesmo
> `Stream #0:0: Video: hevc (Main), d3d11(...), 1920x1080 ... 15000 kb/s, 60 fps`
> da primeira. Nenhum `Address already in use`, nenhum `bind failed`, nenhum
> ffmpeg órfão, e `Get-NetUDPEndpoint -LocalPort 9000` vazio antes e depois de
> cada uma. A promessa está cumprida no SO que importa.

---

### Veredito da fase

| Passo | Precisa do Mac? | Resultado |
|---|---|---|
| F2.1 doctor (11 checagens) | não | ✅ 11 OK, código 0 — depois de corrigir o `host` do toml |
| F2.2 dry-run == Fase 0 | não | ✅ idêntico, só o `-nostdin` a mais |
| F2.3 jogo no OBS | **sim** | ✅ RE2 borderless, 57.1 fps inst., 14.7 Mbps, drop=0, imagem no OBS |
| F2.4 Ctrl+C limpo | não | ✅ 0.27–0.67 s, `signal 2` tratado, zero órfão |
| F2.5 duas rodadas seguidas | não | ✅ a segunda sobe na hora |

Os cinco passando = **Fase 2 fechada**, e a Fase 3 (áudio) começa — que é a que
exige instalar driver e reiniciar a máquina.

**Estado em 30/08: os cinco passaram — a Fase 2 está fechada.** A Fase 3 (áudio)
pode começar.

Duas coisas saem daqui e não cabem no ✅:

1. **Borderless virou requisito**, não preferência (§F2.3-bis). Fullscreen
   exclusivo derruba a captura com `DXGI_ERROR_ACCESS_LOST`.
2. **Os contadores do Mac do F2.3 não foram coletados** — a imagem foi confirmada
   a olho. Não bloqueia a fase, mas é a metade do §4d que continua faltando.

> 🟡 **Uma observação para o F2.3, não um defeito.** Nas rodadas de ~5 s **sem
> receptor conectado** o ffmpeg registrou `dup=0 drop=1` — um frame em 284 — e
> `speed` entre 0.83x e 0.98x, subindo ao longo da corrida. Não vale como medida:
> a corrida é curta demais (regra 6), a tela estava parada (regra 7) e o bitrate
> real ficou em ~0.9 Mbps, longe do teto de 15M. Está anotado só para que o
> `drop=1` não apareça como novidade no F2.3.

---

## F1 — `lanstream doctor` no Windows ✅ **passou em 29/08 — a Fase 1 fechou**

> **Nove checagens, nove OK, código de saída 0.** ffmpeg ainda em 8.1,
> `hevc_nvenc` escolhido, `ddagrab` e SRT presentes, regra de firewall viva, IP
> ainda **192.168.0.12**, porta 9000 livre. O diagnóstico automático reproduz em
> segundos o que a Fase 0 levantou na mão. Saída integral e análise em
> [`docs/fase1.md`](fase1.md) §1.
>
> 🟡 **Um achado:** o `[network] host` tem dois significados que brigam entre si —
> a linha de alcance quer a *outra* ponta, as URLs querem o *sender*. No Windows
> não existe valor que sirva aos dois. Não bloqueou a Fase 1; a Fase 2 precisa
> separar em `host` + `peer` antes de gerar essa URL para valer.

Não mede rede nem qualidade: mede se o diagnóstico automático concorda com o que a
Fase 0 descobriu na mão. É rápido (segundos) e não precisa de mim do outro lado.

```powershell
git pull
winget install --id=astral-sh.uv -e     # só na primeira vez
uv venv
uv pip install -e ".[dev]"
.venv\Scripts\lanstream doctor
```

Cole a saída inteira. O que ela **precisa** dizer, porque a Fase 0 já provou cada
item pelo caminho difícil:

| Linha | Esperado | Se vier diferente |
|---|---|---|
| `ffmpeg` | **8.1** | Se aparecer 9.x, o `winget upgrade` reintroduziu o bug de NVENC do `baseline` §2 — o próprio doctor avisa |
| `encoders de hardware` | inclui `hevc_nvenc` | build errado do ffmpeg |
| `encoder escolhido` | `hevc_nvenc` | a cadeia de fallback caiu — HEVC é requisito (§3.3 do PLANO) |
| `ddagrab` | presente | build `essentials` em vez do `full` |
| `protocolo SRT no ffmpeg` | presente | idem |
| `firewall` | regra "lanstream SRT" existe | a regra foi criada na Fase 0; se sumiu, o comando está na própria mensagem |
| `porta 9000/UDP` | livre | sai como **AVISO**, não falha: com o sender no ar a porta está ocupada e isso é o esperado. Sem sender, é ffmpeg órfão segurando a porta (§4e) |
| `IPs locais` | inclui **192.168.0.12** | o IP mudou — atualize `[network] host` do meu lado |
| `alcance até ...` | precisa de `[network] host` preenchido | ⚠️ a instrução original era pôr `host = "192.168.0.21"` (o Mac) — funciona para o alcance, mas imprime a URL de OBS errada. Ver o achado em `fase1.md` §1 |

O código sai **1** se houver FALHA e **0** caso contrário, então dá para usar como
preflight antes de subir o sender na Fase 2.

> ⚠️ O `doctor` **não** abre conexão SRT nem toca na porta além de um bind de teste
> instantâneo. Pode rodar com o sender no ar sem derrubar nada — ao contrário do
> `srt-live-transmit`, que consome a única conexão que o sender aceita (§4e).

---

## T1 — HEVC a 15 Mbps ✅ **respondido em 30/08 pelo F2.3, do lado do sender**

> **O refazer aconteceu, embutido no F2.3.** Com o RE2 em borderless o caminho
> carregou **14.5–15.2 Mbps sustentados** por 3 minutos com o sender em **57.1 fps
> instantâneos, speed 1.000x e `drop=0`** — o cenário do "Sender em 57–58 fps /
> speed ~0.99x" que esta tabela define como configuração de produção. O que falta
> para bater o critério inteiro é o "receptor em 0 drops": os contadores do Mac
> não foram coletados. **15M CBR é o default de produção**, com essa ressalva.

## T1 (registro original) — ⚠️ executado em 29/08, **inconclusivo — refazer**

> **Rodado. Não decidiu nada.** Sender deu `fps=52 speed=0.995x` em 37 s, mas o
> stream carregou só **1.67 Mbps** — desktop parado, e o `hevc_nvenc` em CBR não
> preenche com stuffing, então `-b:v 15M` é teto e não piso. A rodada pediu 10% do
> teto de 17 Mbps que ela deveria estressar. Detalhe em `baseline.md` §4f.
>
> **Para refazer, a tela precisa estar em movimento** (vídeo 1080p60 em tela cheia)
> — ou pule direto para o **T3**, que gera o bitrate de graça e ainda ataca o risco
> existencial. Um `0 drops` com a tela parada é falso positivo.

```powershell
git pull
powershell -ExecutionPolicy Bypass -File scripts\win-test-video.ps1 `
  -Gpu nvidia -Codec hevc -Bitrate 15M -LatencyMs 1200
```

**Eu meço no Mac:** `RCV-DROPPED`, erros de decode, fps recebido.
**Você me passa do sender:** as linhas de `fps=` e `speed=`.

| Resultado | Significa |
|---|---|
| Sender em **57–58 fps / speed ~0.99x** e receptor em **0 drops** | ✅ **Configuração de produção encontrada.** A rede sai do caminho crítico e a Fase 0 fecha. |
| Sender freado (**< 55 fps**, com bitrate real no caminho) | O caminho não aguenta nem 15 Mbps → vai para o **T5**. |
| Receptor com drops mesmo sem freio | Buffer ainda pequeno para o caminho → subir para 2000 ms e repetir. |

> Por que HEVC: a ~15 Mbps ele rende aproximadamente o que o H.264 renderia a 25.
> Dentro do teto de ~17 Mbps do §4e, é o que torna 1080p60 viável. Deixou de ser
> preferência do §3.3 e virou requisito.

---

## T2 — HEVC a 20 Mbps 🟡 só se o T1 passar limpo

```powershell
powershell -ExecutionPolicy Bypass -File scripts\win-test-video.ps1 `
  -Gpu nvidia -Codec hevc -Bitrate 20M -LatencyMs 1200
```

Serve para achar a margem real, não para usar em produção. Se passar sem freio,
o teto de 17 Mbps do §4e era conservador e vale reabrir o número. Se frear, o teto
está confirmado por um terceiro método e o T1 vira o default definitivo.

> 🔼 **Subiu de prioridade depois do T4.** O receptor registrou **picos de
> 17.47 Mbps passando limpos** (§4h) — acima do próprio teto que o §4e estimou.
> Pico não é taxa sustentada, então isso não derruba o número, mas indica que ele
> é piso conservador. O T2 virou a forma mais direta de descobrir a margem real.

---

## T3 — Jogo real ✅ **fechado em 30/08 — o jogo 3D moderno era o que faltava**

> **O pendente do T3 caiu junto com o F2.3.** Resident Evil 2 remake (RE Engine),
> 3 minutos, 14.5–15.2 Mbps sustentados, 57.1 fps instantâneos, `drop=0`, imagem
> confirmada no OBS do Mac. O `ddagrab` captura jogo 3D moderno — **em
> borderless**. Em fullscreen exclusivo, não: `DXGI_ERROR_ACCESS_LOST` mata a
> captura na transição (§F2.3-bis). Anti-cheat continua não testado — o RE2
> single-player não carrega nenhum.

## T3 (registro original) — ✅ **executado em 29/08 — a DDA captura**

> **Risco existencial eliminado** (§4g): o `ddagrab` entregou frame de jogo por 3
> minutos, confirmado visualmente. Mas o título testado (Resident Evil clássico:
> 4:3 em pillarbox, cenários pré-renderizados, fonte de 30 fps) é quase o caso mais
> fácil possível e só gerou **8.96 Mbps**. **Falta refazer com jogo 3D moderno**,
> de preferência com anti-cheat — é lá que a captura costuma ser bloqueada.

**É o teste mais importante da lista.** Tudo que foi medido até aqui usou o
desktop. O `ddagrab` usa a Desktop Duplication API, e ela se comporta diferente com
um jogo em fullscreen exclusivo — em alguns títulos ela simplesmente **não entrega
frame nenhum**. Se falhar aqui, a arquitetura muda (§6 do PLANO, Plano B).

Com a configuração que passar no T1:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\win-test-video.ps1 `
  -Gpu nvidia -Codec hevc -Bitrate 15M -LatencyMs 1200
```

Depois abra **o jogo que você realmente joga**, em fullscreen exclusivo (não
borderless — borderless é o caso fácil e já está coberto pelo desktop).

| O que observar | Significa |
|---|---|
| Imagem do jogo chega no Mac | ✅ Risco eliminado, Fase 0 fecha de verdade |
| Tela preta ou congelada no Mac | ❌ DDA bloqueada → testar borderless windowed; se só borderless funcionar, vira restrição documentada do projeto |
| Erro no sender ao entrar no jogo | ❌ Provável anti-cheat bloqueando captura → **Plano B** |

**Também mede o que o desktop não conseguia:** os ~52–58 fps medidos até agora
podem ser artefato da DDA só entregar frame quando a tela muda. Com um jogo
renderizando a 60 fps contínuos, o número pode subir. Anote o `fps=` do sender.

---

## T4 — Estabilidade de 10 minutos ✅ **passou em 29/08**

> **10:26 contínuos, zero erro no log, `speed` em 1.000x do minuto 1 ao 10** (§4h).
> Sem degradação de fps, bitrate ou drift. Terminou por desconexão do receptor, não
> por colapso. **O critério de saída da Fase 0 está batido** — para este bitrate
> (~8.4 Mbps) e este jogo. Falta repetir com 15 Mbps reais no caminho.

Com a config vencedora, deixe rodando **10 minutos sem tocar em nada**. Eu mantenho
o receptor conectado e acompanho drops acumulados e drift.

O PLANO define a saída da Fase 0 como "estável por 10 minutos". Todas as corridas
até agora duraram de 13 a 32 segundos, e sempre terminaram porque **eu** fechei o
receptor (§4e) — nunca por colapso. Estabilidade longa segue não medida.

---

## T5 — Mac no cabo ⚪ só se o T1 frear

Precisa de **adaptador USB-C → Ethernet** (o MacBook Air não tem porta).

O §4c isolou a perna **roteador → Mac** (downlink do AP) como a única suspeita que
sobrou: o cabo do Windows carrega 93.5 Mbps de entrada e o Wi-Fi do Mac transmite
60 Mbps de UDP sem perder pacote. É o único trecho que os dois testes não
compartilham.

Com o Mac no cabo, repetir o `iperf3` nos dois sentidos:

```powershell
iperf3 -c <IP-DO-MAC> -t 30
iperf3 -c <IP-DO-MAC> -u -b 25M -t 30
```

Se a assimetria sumir, o problema era o Wi-Fi e o teto de 17 Mbps deixa de existir.

---

## T6 — Varredura de buffer ⚪ adiar para a Fase 7

Sabemos que 120 ms é pouco e 1200 ms basta. O mínimo necessário não foi medido.
Não é bloqueante: pelo §3.1 do PLANO latência é barata aqui, então 1200 ms como
default não custa nada. Fica registrado para não parecer esquecido.

---

## Tabela para preencher

| Teste | Codec | Bitrate | Buffer | fps sender | speed | drops (Mac) | erros decode | Veredito |
|---|---|---|---|---|---|---|---|---|
| F2.3 | hevc | 15M | 1200 | **57.1 inst.** | 1.000x | não medido | não medido | ✅ **RE2 borderless, 3 min, 14.5–15.2 Mbps, drop=0, imagem no OBS** |
| F2.3-bis | hevc | 15M | 1200 | — | — | — | — | ❌ fullscreen exclusivo: `DXGI_ERROR_ACCESS_LOST` aos 4.3 s |
| T1 | hevc | 15M | 1200 | 52 | 0.995x | não medido | não medido | ⚠️ inconclusivo — só 1.67 Mbps no caminho (§4f) — **respondido pelo F2.3** |
| T2 | hevc | 20M | 1200 | | | | | |
| T3 | hevc | 15M | 1200 | 52 | 0.999x | **0** | **0** | ✅ DDA captura o jogo (§4g). 155k pacotes, perda zero. Média 9.6 Mbps, pico 15.1 |
| T4 | hevc | 15M | 1200 | 56 (56.2 inst.) | 1.000x | **0** | **0** | ✅ **10:26 contínuos, 508k pacotes, perda zero, sem deriva (§4h)** |
