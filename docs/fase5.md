# Fase 5 — Robustez

O que a Fase 2 entregou funciona enquanto alguém olha. Esta fase existe para a
sessão sobreviver ao que acontece quando ninguém está olhando.

O problema central não é hipotético e já estava medido: **o ffmpeg em modo SRT
`listener` morre toda vez que o receptor desconecta**, porque trata a queda do
caller como erro fatal (`proximos-testes.md`, regra 1). Trocar de cena no OBS,
um engasgo de Wi-Fi ou a captura perder o desktop derrubam o sender, e alguém
precisa ir até o Windows.

Data: 2026-08-31

---

## 1. `--watch`: o supervisor

`lanstream send --watch` roda o ffmpeg em laço até o Ctrl+C ou até um motivo que
não se reergue. Três decisões vieram de medição, não de gosto:

**O motivo sai classificado, e a classificação decide.** O supervisor lê as
últimas linhas do stderr do ffmpeg e traduz:

| o que o ffmpeg disse | motivo | reergue? |
|---|---|---|
| `DXGI_ERROR_ACCESS_LOST` / `887a0026` | a captura perdeu o desktop | sim |
| `I/O error` no muxer | o receptor desconectou | sim |
| `Address already in use` | há um ffmpeg órfão | **não** |
| `Could not find audio only device` | o device de áudio sumiu | **não** |
| qualquer outra coisa | não reconhecido | sim |

Os dois "não" são os que se repetiriam **iguais para sempre**: reerguer aí é
ruído, não robustez. O default do desconhecido é reerguer, porque o `--watch`
existe justamente para sobreviver ao que ninguém previu — e o teto de tentativas
mais o backoff impedem que um erro permanente vire laço apertado.

**O backoff se reseta depois de uma sessão de verdade.** Uma sessão que rodou
meia hora e caiu não merece a mesma espera de uma que morre em dois segundos.
Sem o reset, uma noite de jogo com três quedas espaçadas terminaria esperando um
minuto para reerguer, e vinte quedas ao longo de horas fariam o supervisor
desistir como se fosse um erro permanente.

> 🐛 **Este item nasceu com defeito e foi pego no teste.** O laço era
> `for tentativa in range(TENTATIVAS)` e o reset fazia `tentativa = 0` — que num
> `for` **não tem efeito nenhum**, porque a iteração seguinte reatribui a
> variável. Eu tinha até escrito um comentário `noqa` afirmando que funcionava. O
> teste da §1.1 é o que mostrou: com teto de 5 tentativas seguidas, uma sequência
> de execuções saudáveis precisa passar de 5 execuções — e passava só depois de
> trocar por um contador explícito.

**A porta é conferida antes de subir.** O ffmpeg leva um instante para fechar o
socket depois de morrer, e subir o próximo em cima disso dá `Address already in
use` — que a tabela acima classifica como "não reerguer", e a sessão morreria por
um problema que some sozinho em um segundo. O supervisor espera até 15 s pela
porta vagar; se ela não vagar, aí sim é órfão, e ele diz o comando que resolve.

### 1.1 O que foi verificado, e como

Com um ffmpeg falso que escreve no stderr o que o de verdade escreveria e morre:

```
  io            -> 5 execuções, 5 reinícios, reergue     (esperado: reergue)
  dxgi          -> 5 execuções, 5 reinícios, reergue     (esperado: reergue)
  porta         -> 1 execução,  0 reinícios, PARA        (esperado: PARA)
  desconhecido  -> 5 execuções, 5 reinícios, reergue     (esperado: reergue)

  intervalos entre reinícios: 0.17  0.27  0.48  0.47  0.41
    (backoff de 0.1 dobrando até o teto de 0.4; cada medida inclui
     ~0.07 s de partida do processo)

  reset: 8 execuções com teto de 5 tentativas SEGUIDAS -> o contador zera
```

**O que isto não prova:** nada sobre o ffmpeg de verdade, o ddagrab ou o SRT. O
teste exercita a máquina de decisão, que é onde os erros de lógica moram; a prova
de que o par se reergue sozinho é a do §F5 no Windows, com o OBS do outro lado.

## 2. O log: para quem não estava olhando

O console serve para quem está olhando. Numa sessão de três horas ninguém
acompanha o terminal, e quando algo some do ar a pergunta é sempre sobre o
passado — daí `logs/lanstream.log`, rotativo.

Duas decisões:

* **A linha de progresso entra por amostragem** (30 s por padrão). Ela se
  reescreve várias vezes por segundo; guardá-la inteira encheria o arquivo e a
  rotação descartaria justamente as linhas de **erro**, que são raras e são as
  que explicam. Amostrada, ela vira um batimento de fps/bitrate ao longo do tempo.
  As linhas que não são progresso entram todas.
* **Não conseguir escrever o log avisa e segue.** Quem está prestes a jogar não
  quer descobrir que o `send` não sobe porque uma pasta não pôde ser criada.
* **`--verbose` troca o batimento pelo registro completo** — no arquivo, não no
  console. O console já recebe tudo do ffmpeg direto; duplicar as mesmas linhas
  por um segundo caminho seria ruído. A flag serve para quando se está caçando um
  engasgo de segundos e a amostra de 30 s é grossa demais. Medido: 50 linhas de
  progresso viram 1 no arquivo sem a flag, e 50 com ela.

A primeira linha do arquivo é sempre o comando que rodou — é a primeira coisa que
se quer saber ao reler. Verificado com o ffmpeg falso, um arquivo de sessão sai
assim:

```
2026-08-31 20:08:13 INFO  === sessão iniciada (watch=True) ===
2026-08-31 20:08:13 INFO  comando: …/fake-ffmpeg.py io
2026-08-31 20:08:13 INFO  [batimento] frame=  100 fps= 60 q=20.0 size=1024kB time=00:00:01.66
2026-08-31 20:08:14 INFO  [srt] Error submitting a packet to the muxer: I/O error
2026-08-31 20:08:14 WARNING [watch] o ffmpeg saiu (1) depois de 0s: o receptor desconectou (o listener SRT atende um cliente só). |   reerguendo em 0s (tentativa 1 de 3)
2026-08-31 20:08:15 INFO  resumo: 3 execuções, 3 reinício(s), 0.0 min no ar
2026-08-31 20:08:15 INFO  resumo:   - o receptor desconectou (o listener SRT atende um cliente só) (3x)
```

Rotação verificada: 2,4 MB escritos com `max_mb = 1` produziram `lanstream.log`
+ `.1` + `.2`.

## 3. Auto-start: atalho na Inicializar, não tarefa agendada

`lanstream install-autostart` escreve um `.cmd` na pasta Inicializar do usuário
(`--dry-run` mostra o conteúdo, `--remove` desfaz). O Task Scheduler faria isso
"mais direito" e seria **pior aqui**: tarefa agendada roda sem console, e sem
console o `CTRL_C_EVENT` não tem onde chegar — que é exatamente o mecanismo que a
Fase 2 mediu para o ffmpeg encerrar limpo, escrevendo o trailer e soltando a
porta (`fase2.md` §5). Uma janela de console de verdade dá para ver e dá para
encerrar do jeito já testado.

O `.cmd` chama `python -m lanstream.cli` em vez do `lanstream.exe`, porque o
console script depende de como o pacote foi instalado e o módulo funciona em
qualquer caso. E termina com `pause`: se falhar na partida, sem isso a janela
fecha antes de alguém ler o motivo, e o sintoma vira "não subiu".

### Três coisas que a revisão obrigou a consertar

Todas com o mesmo formato de falha: **quebra depois de um reboot, longe de quem
poderia entender.**

1. **O `--config` vai explícito, com o caminho resolvido na instalação.** Sem ele
   o sender dependeria de onde o `cd` parou para achar o toml — e um diretório
   errado não daria erro: cairia nos defaults embutidos e subiria com host, porta
   e device errados, calado. Instalar de fora do projeto agora é recusado.
2. **O arquivo é escrito em `mbcs`, não UTF-8.** O `cmd.exe` lê batch na codepage
   ANSI do console; num caminho como `C:\Users\João\...` o UTF-8 vira mojibake e
   o `cd` falha no login. E caminho com `%` é recusado: o batch expande variável
   mesmo dentro de aspas.
3. **`--remove --dry-run` apagava mesmo assim.** O `--dry-run` ensina que nada é
   tocado; apagar sob ele seria a pior traição possível dessa expectativa.

## 4. A prova real: a rede caiu 30 s e o par voltou sozinho

Rodada de 01/09, com o OBS do Mac conectado e `send --watch` no ar. A queda foi
provocada por script destacado (`Disable-NetAdapter` no adaptador `Ethernet`,
30 s, `Enable-NetAdapter`), com tarefa agendada de segurança para religar caso o
script morresse no meio — a máquina precisa se restaurar sem depender de quem a
derrubou.

```
09:03:43.789   adaptador Ethernet OFF
09:03:43.579   SRT começa a acusar CChannel::sendto failed
09:03:48       ffmpeg morre: I/O error                        (5 s depois da queda)
09:03:48       [watch] classifica e decide: reerguendo em 1s  (tentativa 0 de 20)
09:03:50       ffmpeg novo de pé, escutando na 9000 — com a rede ainda FORA
09:04:14       adaptador ON
09:04:25       IP de volta (192.168.0.12)
09:04:26       Output #0 → o OBS reconectou sozinho
09:04:56       60 fps, speed=1x, estável
```

**Stream de volta 43 s depois da queda, 12 s depois de o IP voltar, com zero
intervenção nas duas máquinas.** É o critério de saída da fase.

Duas coisas que o teste mostrou e que não estavam previstas:

**O supervisor reergue durante o apagão, e isso é o certo.** O ffmpeg novo subiu
às 09:03:50 com a rede ainda fora e ficou segurando a porta esperando o caller.
Não era óbvio que o bind em `0.0.0.0:9000` funcionaria com o adaptador
desabilitado — funciona, e é o que faz o par voltar em 12 s em vez de esperar
mais um ciclo de backoff depois que a rede volta.

**A classificação acerta a ação e erra a frase.** O `[watch]` disse *"o receptor
desconectou (o listener SRT atende um cliente só)"*, e o receptor não tinha
desconectado: quem caiu foi a placa de rede desta máquina. O ffmpeg entrega o
mesmo `I/O error` nos dois casos, então o stderr sozinho não distingue — quem ler
o log depois de uma queda de rede vai procurar do lado errado. Distinguir é
barato e ainda não foi feito: se o próprio host perdeu o IP, a frase é outra.

> Antes da queda provocada, a mesma sessão já tinha reerguido duas vezes por
> desconexão real do OBS (08:52:30 e 08:56:51), as duas em ~25 s. A lógica da §1,
> verificada com ffmpeg falso, se comporta igual com o ffmpeg de verdade.

## 5. O achado que o log de arquivo revelou: o áudio perde quadro na captura

O `[logs]` da §2 existe para responder perguntas sobre o passado. Na primeira
sessão real ele respondeu uma que ninguém tinha feito.

Durante a sessão inteira, o ffmpeg repetiu:

```
[in#0/dshow] real-time buffer [virtual-audio-capturer] [audio input]
             too full or near too full (75% of size: 3041280)! frame dropped!
```

1105 linhas em ~15 minutos. **O vídeo esteve perfeito o tempo todo** — 60 fps
cravados, `speed=1x`, nenhum quadro perdido. O áudio, não: chegou **picotado e
dessincronizado** no OBS do Mac. O drop é só do áudio, e não aparece em nenhum
indicador de saúde do stream — o vídeo perfeito e o `speed=1x` dizem que está
tudo bem, e não está.

> A primeira leitura desta sessão foi "soa contínuo", e ela estava errada — a
> conferência de ouvido foi refeita e o picote é audível. Registro o erro porque
> ele quase virou doc: por 20 minutos este documento afirmou que o drop não
> machucava, apoiado numa impressão, contra dois números que já diziam o
> contrário (o buffer preso em 75–92% e o déficit de bytes abaixo).

**A causa, confirmada por intervenção.** O device dshow abre quando o processo
sobe, mas o listener SRT trava o ffmpeg até o caller chegar. Nesse intervalo o
áudio já está capturando e ninguém consome: a fila enche, e **ela nunca drena**,
porque depois da conexão o consumo é exatamente igual à produção — tempo real.
O backlog formado na espera fica lá até o fim da execução.

Não é correlação. Na mesma sessão, mesmo comando, mesma máquina, mudando só a
espera (matei o ffmpeg para o supervisor reerguer com o OBS já reconectando):

| execução | espera pelo caller | drops de áudio | o que se ouviu no Mac |
|---|---|---|---|
| 08:49:30 | 2 min 45 s | satura em 100% | — |
| 08:52:32 | 23 s | pina em 75% | picotado |
| 09:03:50 | 36 s | pina em 92%, **5325** em 16 min | picotado e dessincronizado |
| **09:20:31** | **5 s** | **0** | **limpo, ~4 s atrasado** |

### A aritmética que fecha os dois sintomas

O buffer do dshow é o `rtbufsize` default, 3.041.280 bytes. O áudio ocupa
192.000 B/s (48 kHz × 2 canais × 2 bytes). Portanto o buffer cheio são **15,8 s
de áudio**, e o comportamento se parte em dois regimes:

```
espera <  15,8 s  ->  não satura: sem drop, e o áudio sai ATRASADO pela espera
espera >  15,8 s  ->  satura: drop contínuo para sempre, atraso preso em ~15,8 s
```

As quatro execuções acima caem exatamente nos dois lados, e o caso de 5 s prevê
o atraso relatado: **5 s de espera, ~4 s de atraso ouvido.** O `frame dropped`
repetido não era a doença — era o `aresample=async=1` descartando quadro para
tentar alcançar um áudio que estava 12 s atrás.

> **Um sintoma que nenhum indicador de saúde acusa.** Durante os 16 minutos com
> 5325 drops, o vídeo esteve em 60 fps cravados e `speed=1x`. O `doctor` passa, o
> stream "está bem", e o áudio chega quebrado.

### Isto explica a contradição que trancou o F3.4

O `fase3.md` §13 registrou que o offset de áudio **muda a cada execução**, por um
fator de vinte e com o sinal trocado, e por isso nenhum número serve no
`offset_ms`. A hipótese de lá era o tempo variável de abertura do device dshow.

Há uma explicação melhor, e ela é a mesma daqui: **o que varia a cada execução é
quanto o sender esperou o OBS conectar**, e essa espera vira atraso do áudio.
Cada rodada mediu a sua própria espera.

E o §10 do mesmo documento ganha sentido retroativo. Lá, a gravação **local** de
60 s — argv idêntico ao do `send`, só trocando o SRT por arquivo — deu mediana
**−0,3 ms**, sincronismo perfeito, enquanto toda rodada por SRT dava dezenas ou
centenas de ms. A diferença entre as duas: **a gravação em arquivo não espera
caller nenhum.** Saída de arquivo abre na hora, backlog zero.

> Isto é hipótese forte, não causa medida: as magnitudes do §13 são de dezenas a
> centenas de ms, e esperas de segundos previriam mais. Pode haver um segundo
> termo. O que já não se sustenta é tratar o `offset_ms` como constante de config.

## 6. O conserto: um teto na fila de captura

`[audio] rtbuffer_ms`, default **500 ms**, vira `-rtbufsize` em bytes no bloco de
entrada do dshow (500 ms × 192.000 B/s = 96.000). A conversão de ms para bytes
mora no `audio.py` porque a unidade do ffmpeg é byte e a unidade em que se pensa
é tempo — o `RAW_BYTES_POR_S` documenta a suposição de formato do device.

**Por que um teto resolve.** Descartar áudio *enquanto ninguém assiste* não custa
nada: o que importa é que a conexão comece com áudio fresco. O teto não impede a
fila de encher na espera, ele impede que ela guarde 15,8 s de passado.

Duas validações entraram junto, as duas por falha possível e silenciosa:

* faixa de 50 a 20000 ms — abaixo de 50 a fila descartaria em operação normal, e
  não só na espera; acima de 20000 já passa do default do ffmpeg e não limita nada;
* recusa `rtbuffer_ms < buffer_ms` — uma fila menor que um bloco do device
  descartaria cada bloco assim que ele chegasse.

### O que foi verificado, e o que não foi

**Verificado:** o argv que sobe traz `-rtbufsize 96000`; o `example.toml` continua
batendo com os defaults do código (`config show -c lanstream.example.toml`); a
sessão real reiniciada às 09:30:54 rodou com **0 drops**, 60 fps e `speed=1x`; e
**o áudio voltou a chegar limpo e em sincronia no OBS do Mac** — conferido de
ouvido, que é a mesma ponta que tinha diagnosticado o problema.

**Não verificado:** o caso de espera longa, que é justamente o que o teto ataca.
A execução que confirmou o conserto pegou o OBS em menos de 1 s de espera, e com
espera zero o código antigo também ficaria limpo.

> 🔬 **Uma tentativa de testar isso não valeu, e fica registrada para não ser
> repetida.** Subi um sender de teste na porta 9001 com 60 s de espera
> deliberada. O teto funcionou na espera (fila em 100% e parada lá, 11 descartes
> em 60 s), mas apareceram 113 linhas de drop depois do caller conectar — o que,
> se fosse limpo, apontaria para o teto trocar atraso por picote. **Não era
> limpo:** o teste rodou junto com o sender de verdade, dois ffmpeg abrindo o
> mesmo `virtual-audio-capturer` e dois nvenc na mesma GPU. A contenção explica
> os 113 sozinha. Um teste de espera longa precisa da máquina só para ele.

**O que a aritmética garante mesmo sem esse teste:** o backlog máximo caiu de
15,8 s para 0,5 s. O atraso de 12 s não pode mais acontecer. Se sobrar picote em
alguma sessão, é outro mecanismo — e o caminho seria inverter o SRT para `caller`
no Windows, porque em modo caller o ffmpeg não fica bloqueado esperando: conecta
ou falha rápido, e o supervisor já sabe reerguer.

## 7. O que falta na fase

- [x] **A prova real:** feita em 01/09 — §4.
- [ ] Rodar o `install-autostart` no Windows e conferir que ele sobe no login.
- [x] **Limitar o `rtbufsize` do dshow** — feito em 01/09, §6. O áudio voltou a
      chegar limpo e em sincronia.
- [ ] Provar o teto no caso de **espera longa**, com a máquina só para o teste
      (§6). Hoje ele está justificado pela aritmética e pela sessão curta.
- [ ] Refazer a medição do F3.4 agora: se a espera era o termo que faltava, o
      offset deve parar de mudar entre execuções — e o `offset_ms = -135` que
      está no toml desta máquina provavelmente deve ir para 0.

⛔ **O mDNS não será construído.** O próprio item do PLANO já dizia que só valeria
se o IP do Windows mudasse de fato — e ele não mudou em nenhuma rodada. Uma
reserva de DHCP no roteador resolve com zero código e zero peça nova para quebrar.
