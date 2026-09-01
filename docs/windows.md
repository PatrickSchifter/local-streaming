# O que rodar no Windows

Tudo o que a máquina do Windows precisa fazer, em um lugar só. Os comandos são
para colar; o **porquê** de cada um está nos documentos de fase, e este aponta
para lá em vez de repetir.

> Atualizado em 01/09. **Estado:** Fases 0 a 4 fechadas. A Fase 5 bateu o
> critério de saída — a rede caiu 30 s e o par voltou sozinho (`fase5.md` §4).
> No caminho apareceu e foi corrigido um defeito de áudio que nenhum indicador
> acusava (§2.2). Os itens abertos estão no §2.

---

## 1. Toda vez, antes de qualquer coisa

```powershell
cd C:\Users\schif\Projetos\local-streaming
git pull
uv pip install -e ".[dev]"
lanstream doctor
```

O `doctor` tem que fechar sem FALHA. Se ele acusar `porta 9000/UDP ocupada` sem
sender no ar, sobrou ffmpeg órfão: `Get-Process ffmpeg | Stop-Process`.

## 2. O que está aberto aqui

### 2.1 O `install-autostart` ✅ **verificado em 01/09**

Instalado e conferido no login desta máquina: console de verdade, `send --watch`
rodando, argv com o `--config` absoluto.

```powershell
lanstream install-autostart --dry-run   # confira o caminho do toml na linha do send
lanstream install-autostart
lanstream install-autostart --remove    # desfaz
```

> ⏱️ **Espere ~40 s depois do login antes de concluir que falhou.** Medido aqui:
> login às 10:09:58, sender no ar às 10:10:42. O Windows não dispara os itens da
> pasta Inicializar no instante do login. E se a janela for fechada antes de o
> sender inicializar, **ela não deixa linha no log** — a sessão só é registrada
> depois que o logging sobe, então não adianta procurar rastro ali.

O `.cmd` termina com `pause` de propósito: se falhar na partida, sem isso a
janela fecha antes de alguém ler o motivo, e o sintoma vira "não subiu"
(`fase5.md` §3).

### 2.2 O atraso do áudio ✅ **corrigido em 01/09** — falta uma prova

Diagnosticado e consertado na sessão de 01/09 (`fase5.md` §5 e §6). Fica aqui
porque o sintoma é fácil de reencontrar e o conserto tem uma ponta solta.

**O que era:** o device dshow abre quando o `send` sobe, mas o listener SRT trava
o ffmpeg até o OBS conectar. O áudio capturado nessa espera virava fila que
**nunca drenava** — o consumo depois da conexão é tempo real, igual à produção.

```
fila default do ffmpeg: 3.041.280 B ÷ 192.000 B/s = 15,8 s de áudio

espera <  15,8 s  ->  áudio limpo, ATRASADO pelo tempo da espera
espera >  15,8 s  ->  satura: picote contínuo + ~15,8 s de atraso
```

**O conserto:** `[audio] rtbuffer_ms = 500` (default), que vira `-rtbufsize` e
limita o backlog máximo a meio segundo. Descartar áudio enquanto ninguém assiste
não custa nada; o que importa é a conexão começar com áudio fresco.

**A ponta solta:** o caso de **espera longa** ainda não foi provado — a execução
que confirmou o conserto pegou o OBS em menos de 1 s. Precisa da máquina só para
o teste, sem o sender de verdade rodando junto (`fase5.md` §6 registra a
tentativa que não valeu, para não ser repetida).

**Se o sintoma voltar,** ele não aparece em indicador nenhum — durante 16 min com
5325 quadros de áudio descartados o vídeo esteve em 60 fps cravados, `speed=1x`,
e o `doctor` passando. Procure no log:

```powershell
$l = Get-Content logs\lanstream.log -Encoding UTF8
$i = ($l | Select-String 'sess.o iniciada' | Select-Object -Last 1).LineNumber
($l[($i-1)..($l.Count-1)] | Select-String 'too full').Count
```

Zero é o esperado. Se houver, reinicie o ffmpeg com o OBS já tentando conectar —
`Get-Process ffmpeg | Stop-Process`, que o `--watch` reergue em 1 s.

> O `-Encoding UTF8` não é enfeite: o `Get-Content` do PowerShell 5.1 lê em ANSI,
> o log é UTF-8, e sem ele **nenhum padrão com acento casa** — a contagem sai
> sobre o arquivo inteiro, que acumula todas as sessões, e dá um número grande
> que parece defeito e não é. Mesmo pé no chão do `UnicodeEncodeError` do
> `conferir` (`fase3.md` §10): confundir o encoding do console com o do texto.

## 3. Os comandos que existem

| comando | para quê |
|---|---|
| `lanstream doctor` | ffmpeg, encoders, captura, áudio, SRT, rede e firewall |
| `lanstream doctor --audio` | só a lista de devices de captura |
| `lanstream send` | captura e publica em SRT; Ctrl+C encerra |
| `lanstream send --watch` | **o modo normal de sessão** — reergue o ffmpeg sozinho quando ele cai |
| `lanstream send --dry-run` | só imprime o argv montado |
| `lanstream send --no-audio` | só vídeo, byte a byte o comando da Fase 2 |
| `lanstream send -v` | guarda no log **todas** as linhas de progresso, não a amostra de 30 s |
| `lanstream receive` | recebe e mostra numa janela — o diagnóstico "é a rede ou é o OBS?" |
| `lanstream install-autostart` | faz o `send --watch` subir no login (`--dry-run`, `--remove`) |
| `lanstream config show` | a configuração efetiva, e de qual arquivo ela veio |

O log da sessão fica em `logs\lanstream.log`, rotativo, e a primeira linha é
sempre o comando que rodou. **É o primeiro lugar para olhar depois de qualquer
coisa estranha** — foi ele que revelou o §2.2, invisível no console.

## 4. Regras que já custaram tempo

**Um `send` atende UMA conexão.** O ffmpeg em SRT `listener` trata a desconexão
do caller como erro fatal e morre. O `--watch` resolve isso na prática — ele
reergue e o Media Source do OBS reconecta sozinho a cada 2 s, medido em ~25 s de
ponta a ponta —, mas o processo do ffmpeg é outro a cada rodada, e é por isso que
o contador de quadros zera no log.

> Corolário que já enganou: **uma sonda de fora não distingue "sender morto" de
> "sender ocupado servindo o OBS"**. Se precisar testar por fora, use **outra
> porta** e um segundo `send`, ou pare o OBS antes.

**Fullscreen exclusivo derruba a captura.** `DXGI_ERROR_ACCESS_LOST` em ~4 s. O
jogo tem que estar em **borderless** (`proximos-testes.md` §F2.3-bis).

**Quando as duas pontas discordam, vale a que tem o log.** Já erramos duas vezes
inferindo causa no emissor a partir de sintoma no receptor.

**Não escreva nada no `[audio] offset_ms` sem medir — e talvez nem depois.** O
`fase3.md` §13 mediu o mesmo offset variando por um fator de vinte **entre
execuções**, com o sinal trocado: um valor correto numa conexão errou por 730 ms
na seguinte. O `-135` que está no toml hoje é herança dessa medição e é suspeito.
Enquanto o §2.2 não fechar, ele vale menos que zero.

**O `[watch]` acerta a ação e pode errar a frase.** Ele classificou uma queda da
placa de rede local como "o receptor desconectou", porque o ffmpeg entrega o
mesmo `I/O error` nos dois casos (`fase5.md` §4). Reergueu certo; só não acredite
na causa que ele nomeia sem olhar o resto.

## 5. Sintoma → onde olhar

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| o `send` sobe e morre em ~4 s | `DXGI_ERROR_ACCESS_LOST` — fullscreen exclusivo | borderless |
| o `send` nem sobe, com áudio ligado | o device dshow | `lanstream send --no-audio`: se funcionar, é o áudio e só ele |
| `Address already in use` | ffmpeg órfão | `Get-Process ffmpeg | Stop-Process` |
| o contador de quadros zerou no meio da sessão | o `--watch` reergueu | normal — procure a linha `[watch]` no log para saber por quê |
| `real-time buffer ... frame dropped` no áudio | §2.2, **aberto e audível** | é o picote; reinicie o `send` com o OBS já tentando conectar |
| o doctor diz que o `host` não é desta máquina | o DHCP trocou o IP | a mensagem do doctor lista as hipóteses |
| `doctor --audio` não lista nada | nenhum device de captura | `fase3.md` §1 tem a ordem de tentativa |
| o Mac não recebe imagem | quase sempre o sender morreu | as últimas linhas de `logs\lanstream.log` |

## 6. A config desta máquina, para conferência

```toml
[network]
host = "192.168.0.12"   # esta máquina, o sender
peer = "192.168.0.21"   # o Mac
port = 9000

[audio]
enabled   = true
device    = "virtual-audio-capturer"
buffer_ms = 200
offset_ms = -135        # suspeito — ver §4
```

O `lanstream.toml` é ignorado pelo git de propósito: cada máquina tem o seu. O
`logs/` também, e por um motivo mais forte — o arquivo tem caminho de máquina, IP
e nome de device, e nada disso volta para o repositório. Se a porta mudar para um
teste, **devolva o 9000 depois**: o OBS do Mac aponta para lá.
