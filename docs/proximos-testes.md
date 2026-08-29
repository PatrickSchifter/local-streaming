# Próximos testes — o que rodar no Windows

Ordem de prioridade. Cada teste diz o comando exato, o que eu faço do lado do Mac,
e **o que o resultado decide** — nenhum teste aqui é "por garantia".

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

---

## T1 — HEVC a 15 Mbps 🔴 é o que decide a configuração de produção

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
| Sender freado (**< 55 fps / speed < 0.97x**) | O caminho não aguenta nem 15 Mbps → vai para o **T5**. |
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

---

## T3 — Jogo real em fullscreen exclusivo 🔴 o último risco existencial do projeto

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

## T4 — Estabilidade de 10 minutos 🟡 critério de saída da Fase 0

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
| T1 | hevc | 15M | 1200 | | | | | |
| T2 | hevc | 20M | 1200 | | | | | |
| T3 | hevc | 15M | 1200 | | | | | jogo real |
| T4 | — | — | — | | | | | 10 min |
