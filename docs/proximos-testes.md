# Próximos testes — o que rodar no Windows

Ordem de prioridade. Cada teste diz o comando exato, o que eu faço do lado do Mac,
e **o que o resultado decide** — nenhum teste aqui é "por garantia".

🟡 **O F2 rodou em 30/08: quatro dos cinco passos passaram.** Falta só o
**F2.3**, o único que precisa do Mac do outro lado — é o que segura o critério de
saída da Fase 2. Resultado passo a passo abaixo.

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

## F2 — `lanstream send` no Windows 🟡 **4 de 5 passaram; falta o F2.3**

O código está escrito e verificado no que não depende do Windows (`docs/fase2.md`
§5). Três coisas só esta máquina responde: o `ddagrab`, o NVENC, e o **Ctrl+C do
console do Windows** — o teste daqui foi um SIGINT em POSIX, e o `CTRL_C_EVENT`
percorre outro caminho.

> **Rodado em 30/08.** Das três, duas já responderam: o NVENC é escolhido e monta o
> comando da Fase 0 (F2.1/F2.2), e o `CTRL_C_EVENT` do Windows encerra o ffmpeg
> limpo, sem órfão, sem `terminate` (F2.4/F2.5). Falta o `ddagrab` **com o OBS do
> outro lado**, que é o F2.3.

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
| F2.3 jogo no OBS | **sim** | ⏳ **pendente — é o único que falta para fechar a fase** |
| F2.4 Ctrl+C limpo | não | ✅ 0.27–0.67 s, `signal 2` tratado, zero órfão |
| F2.5 duas rodadas seguidas | não | ✅ a segunda sobe na hora |

Os cinco passando = **Fase 2 fechada**, e a Fase 3 (áudio) começa — que é a que
exige instalar driver e reiniciar a máquina.

**Estado em 30/08:** quatro passaram, o F2.3 está de pé esperando o Mac. Tudo que
esta máquina respondia sozinha, respondeu.

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

## T1 — HEVC a 15 Mbps ⚠️ executado em 29/08, **inconclusivo — refazer**

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

## T3 — Jogo real ✅ **executado em 29/08 — a DDA captura**

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
| T1 | hevc | 15M | 1200 | 52 | 0.995x | não medido | não medido | ⚠️ inconclusivo — só 1.67 Mbps no caminho (§4f) |
| T2 | hevc | 20M | 1200 | | | | | |
| T3 | hevc | 15M | 1200 | 52 | 0.999x | **0** | **0** | ✅ DDA captura o jogo (§4g). 155k pacotes, perda zero. Média 9.6 Mbps, pico 15.1 |
| T4 | hevc | 15M | 1200 | 56 (56.2 inst.) | 1.000x | **0** | **0** | ✅ **10:26 contínuos, 508k pacotes, perda zero, sem deriva (§4h)** |
