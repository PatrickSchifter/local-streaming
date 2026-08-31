# OBS no Mac — a receita medida

Tudo aqui foi lido do OBS **em execução** por `obs-websocket` em 31/08, não
transcrito de menu. Onde a configuração viva difere do que o PLANO pedia, as duas
estão registradas com o motivo.

> ⚠️ **O arquivo de cena mente sobre o presente.** O OBS grava
> `~/Library/Application Support/obs-studio/basic/scenes/*.json` ao sair ou ao
> trocar de coleção. Com o OBS aberto há dias, o que está no disco é o que ele
> **carregou**, não o que está valendo — foi assim que eu li `Monitor Off` num
> OBS que estava com a monitoração ligada (`fase3.md` §9.1). Para conferir de
> verdade, pergunte por `obs-websocket`.

---

## 1. A fonte: Media Source

`Fontes > + > Fonte de Mídia`. Os valores em execução:

| Campo | Valor | Por quê |
|---|---|---|
| **Arquivo Local** | **desmarcado** | a entrada é uma URL, não um arquivo |
| **Entrada** | `srt://<IP-DO-WINDOWS>:9000?mode=caller&latency=1200000` | o Mac é o *caller*; quem escuta é o Windows |
| **Formato de Entrada** | `mpegts` | sem isso o OBS tenta adivinhar e demora a sincronizar |
| **Reiniciar a reprodução quando a fonte ficar ativa** | desmarcado | reiniciar troca de cena em queda de conexão |
| **Encerrar arquivo quando inativo** | **desmarcado** | marcado, o SRT cai ao trocar de cena |
| **Usar decodificação por hardware** | marcado | VideoToolbox no Apple Silicon |
| **Buffer de rede** | `2 MB` (default) | ver §1.1 |
| Tempo de reconexão | `2 s` | ver §1.2 |

> 🔺 **A latência na URL é em MICROssegundos.** `latency=1200000` são os mesmos
> 1200 ms do `[network] latency_ms`. O `srt-live-transmit` usa MILIssegundos na
> mesma opção — é a pegadinha do `baseline.md` §5, e o `lanstream doctor` imprime
> as duas URLs lado a lado justamente para não se errar aqui.

### 1.1 O buffer de rede: 2 MB é o que está rodando, 0 é o que o PLANO pedia

O PLANO §Fase 4 pede `0`, com o argumento de que o buffer já é do SRT. O que está
em execução é o default de **2 MB** — e foi com ele que todas as medições de
31/08 foram feitas, inclusive a de A/V sync que fechou em ±3,5 ms entre blocos.
A 15 Mbps, 2 MB são ~1,1 s de vídeo parado no buffer, ou seja **latência**, não
dessincronia.

Como não foi medido com `0`, fica assim: o valor documentado é o que está rodando
e funciona. Baixar para `0` é knob da Fase 7, com medição de latência ponta a
ponta junto.

### 1.2 O OBS reconecta sozinho — não existe "avise que eu conecto"

Com `reconnect_delay_sec = 2` e `close_when_inactive` desmarcado, a fonte tenta a
cada 2 segundos por conta própria. Medido três vezes em 30–31/08. Consequências
práticas:

* quem sobe o sender **não precisa esperar ninguém** do outro lado;
* o sender em modo `listener` atende **uma** conexão, então o OBS toma essa vaga
  assim que ela existe. Uma sonda externa (`lanstream receive`) rodando junto
  derruba o OBS — e uma sonda que não conecta **não distingue** "sender morto" de
  "sender ocupado servindo o OBS" (`windows.md` §4).

## 2. Áudio da fonte

| Propriedade | Valor | Onde |
|---|---|---|
| Sync Offset | `0` | Propriedades de Áudio Avançadas |
| Monitoramento | ver abaixo | Propriedades de Áudio Avançadas |
| Faixas | todas | idem |

**Monitoramento é armadilha de diagnóstico.** O caminho de monitoração tem
latência própria e **não entra na gravação**. Em 31/08 o áudio soou 2–3 s
atrasado com a monitoração ligada, e a gravação do mesmo momento estava alinhada
em ±20 ms (`fase3.md` §9). Regra: **o que decide é a gravação, nunca o ouvido**.

### 2.1 Duas linhas de log que valem mais que uma gravação

Em `Ajuda > Arquivos de Log > Mostrar Logs`:

```
adding N milliseconds of audio buffering, total audio buffering is now N ms
Source <nome> audio is lagging (over by N ms) at max audio buffering. Restarting source audio.
```

A primeira é o OBS compensando timestamps trêmulos, e ela é **sticky**: só zera
reiniciando a fonte. A segunda é ele desistindo e reiniciando o áudio sozinho —
apareceu duas vezes em 31/08, com 2490 ms e 2204 ms, sempre em conexões de ~45
minutos, e foi o que identificou a deriva do lado do Windows (`fase3.md` §12).

**Se o áudio "atrasar sozinho" no meio de uma sessão, a ação é reiniciar a fonte,
não mexer no `offset_ms`.**

## 3. Como conferir o que está valendo, sem abrir menu

O `scripts/obs-probe.py` já lê o estado da mídia. Para as configurações da fonte,
o mesmo caminho serve com outros pedidos: `GetInputSettings`,
`GetInputAudioSyncOffset`, `GetInputAudioMonitorType`, `GetMediaInputStatus`.

`mediaCursor` é a idade da conexão em milissegundos — e é o jeito mais rápido de
saber se a fonte está recebendo: cursor parado em `0` com estado `PLAYING`
alternando para `ENDED` é o *flapping* de quem tenta e não acha ninguém.

## 4. O mic do Mac: por que ele precisa de atraso, e como medir

O microfone é **local**: o que ele capta chega ao mixer do OBS em milissegundos.
O jogo não: a imagem atravessa captura, encoder, SRT com 1200 ms de buffer, rede,
decodificação e o buffer de rede da fonte. Quem fala no mic aparece adiantado em
relação ao que está acontecendo na tela — e o conserto é **atrasar o mic** pelo
tempo do caminho do vídeo, no `Sync Offset`.

O valor não se estima: mede-se. E dá para medir sem instrumento novo, aproveitando
que a claquete produz **som e imagem no mesmo instante, na mesma máquina**:

```
       o Windows toca a claquete
              │
    ┌─────────┴──────────┐
    │                    │
  imagem               som
    │                    │
  SRT + OBS          pelo AR
  (~1-2 s)          (~ms, o mic capta)
    │                    │
    └──────► gravação ◄──┘
         a diferença é o Sync Offset
```

### O procedimento

1. **Windows:** `lanstream send` com o `claquete.mp4` em tela cheia, e o som
   saindo pela caixa/TV **audível no ambiente** — o mic do Mac precisa ouvir.
2. **Mac:** silenciar o áudio da fonte SRT (`Mic/Aux` fica aberto). Sem isso as
   duas fontes de bipe se misturam na mesma faixa e não há como separá-las.
3. Gravar 2 minutos e medir com o `scripts/av-sync.py medir`.
4. O que sair é quanto o **mic está adiantado**; esse número, positivo, vai no
   `Sync Offset` do `Mic/Aux`.

> Alternativa se o mic não ouvir o Windows (máquinas em cômodos diferentes):
> gravar com **duas faixas de áudio** no OBS — a fonte SRT na 1 e o mic na 2 — e
> medir cada faixa contra o mesmo vídeo. Dá o mesmo número sem depender do ar.

### O resto desta página

- [ ] Escala e ancoragem da fonte na cena (a cena de teste usa tela cheia).
- [ ] Perfil de saída para a Twitch (Apple VT H.264, 6000–8000 kbps, keyframe 2s).

Nenhum dos dois bloqueia o que está acima.
