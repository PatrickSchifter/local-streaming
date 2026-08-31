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

## 2. O que falta na fase

- [ ] Logs rotativos em arquivo + `--verbose` no console.
- [ ] Auto-start opcional no Windows (`lanstream install-autostart`).
- [ ] (Opcional) mDNS — só vale se o IP do Windows mudar de fato; hoje uma
      reserva de DHCP no roteador resolve com zero código.
- [ ] **A prova real:** derrubar a rede por 30 s e o stream voltar sozinho, sem
      tocar em nenhuma das duas máquinas.
