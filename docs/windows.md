# O que rodar no Windows

Tudo o que a máquina do Windows precisa fazer, em um lugar só. Os comandos são
para colar; o **porquê** de cada um está no
[`proximos-testes.md`](proximos-testes.md) §F3 e no [`fase3.md`](fase3.md), e
este documento aponta para lá em vez de repetir.

> Atualizado em 31/08. **Estado:** F3.1, F3.2 e F3.3 passaram. Falta o número do
> **F3.4**.
>
> ✅ **O lado do Windows do F3.4 foi respondido e está limpo.** Medido aqui, sem o
> Mac: a claquete presta (252/252, viés +10,7 ms), o capturador ouve os bipes na
> cadência certa, e o pipeline inteiro gravado local entrega **12 flashes e 12
> bipes em 60 s, mediana −0,3 ms**. O áudio sai desta máquina sincronizado —
> `fase3.md` §10. O que falta explicar está entre o fio e o `.mkv` do OBS.

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

## 2. O passo aberto: já não é aqui

Na rodada de 31/08 o **vídeo** da claquete chegou perfeito no Mac (4 flashes, um
a cada 5 s) e o **áudio** dela não chegou nunca. A árvore abaixo foi percorrida
inteira nesta máquina e **deu limpo nos três degraus** (`fase3.md` §10):

| pergunta | resposta medida |
|---|---|
| o arquivo de claquete presta? | ✅ 252 flashes / 252 bipes, viés +10,7 ms |
| o capturador ouve os bipes? | ✅ `silence_end` a cada 4,99–5,01 s |
| o pipeline entrega as duas trilhas casadas? | ✅ 12/12 em 60 s, **mediana −0,3 ms** |

O terceiro é o que fecha: são 60 s gravados com o argv **idêntico** ao do `send`,
só trocando o SRT por arquivo. É o que o Mac receberia.

> **A leitura de ~−48 dB não era o device parado.** Aqui o piso com nada tocando é
> **−91 dB**; −48 dB é o que se lê quando a média inclui 5 s de silêncio para cada
> 100 ms de bipe. O que decide é `silencedetect`, não `volumedetect`: um bipe de
> 2% de duty cycle sempre parece silêncio numa média.

**Então a hipótese que sobra é do OBS, e é verificável:** no F3.3 o áudio **foi
ouvido**; no F3.4 ele não estava na **gravação**. No OBS ouvir e gravar são
caminhos diferentes — a trilha da fonte precisa estar na track que está sendo
gravada (`Saída > Modo Avançado > Gravação`). Uma fonte audível fora da track
gravada dá exatamente isto: vídeo perfeito, áudio zero, nenhum erro.

### Se precisar refazer a checagem daqui

```powershell
python scripts\av-sync.py conferir claquete.mp4
```

| O que ele diz | Significa | Ação |
|---|---|---|
| ✅ `o arquivo presta` | vídeo, áudio e as duas coisas casando | o arquivo está bom — o problema é a **reprodução**, siga abaixo |
| ❌ `NÃO TEM trilha de áudio` | a claquete nasceu muda | gere de novo (§3, passo 4) e rode o `conferir` de novo |
| ❌ `trilha de áudio existe mas está VAZIA` | a geração falhou no filtro de áudio | me avise: é defeito meu, não seu |

**Se um dia o arquivo prestar e mesmo assim não sair som, é reprodução.** Três
coisas, nesta ordem:

1. **Nada mais fazendo som.** O `virtual-audio-capturer` captura o endpoint
   padrão **inteiro**, não o player: jogo aberto, música, navegador e som de
   notificação entram junto. (Não foi o que houve em 12:16: o piso medido com
   nada tocando era −91 dB, e o GTA estava na tela mas mudo.)
2. **O player está mandando para o dispositivo padrão.** `Configurações > Som >
   Mixer de volume` mostra, por aplicativo, o dispositivo de saída e se está
   mudo. O padrão desta máquina é a **TV PHILCO** (NVIDIA HDMI) — é ele que o
   capturador escuta (`fase3.md` §1).
3. **Se ainda assim não sair som, troque o player** por um que não deixa dúvida:

```powershell
ffplay -fs -autoexit claquete.mp4
```

Com a claquete tocando e o `lanstream send` no ar, me avise: eu gravo 2 minutos
no OBS e meço. **Não precisa esperar eu conectar** — o Media Source do Mac
reconecta sozinho a cada 2 s.

## 3. A fase inteira, na ordem

```powershell
# 1. o device de áudio                                          (F3.1)
lanstream doctor --audio

# 2. colar o nome EXATO no lanstream.toml e ligar:              (F3.2)
#      [audio]
#      enabled = true
#      device  = "virtual-audio-capturer"
lanstream doctor
lanstream send --dry-run

# 3. o áudio chega no OBS?                                      (F3.3)
lanstream send
lanstream send --no-audio      # só se o de cima falhar (ver §4)

# 4. a claquete                                                 (F3.4)
python scripts\av-sync.py claquete claquete.mp4 --segundos 1260
python scripts\av-sync.py conferir claquete.mp4
lanstream send                 # com a claquete em tela cheia

# 5. a rodada real, jogo em BORDERLESS                          (F3.5)
lanstream send
```

Os passos 1 e 2 não precisam de ninguém no Mac. Do 3 em diante, precisam.

## 4. Regras que já custaram tempo

**Um `send` atende UMA conexão.** O ffmpeg em SRT `listener` trata a desconexão
do caller como erro fatal e morre. Cada rodada serve um cliente; para trocar de
cliente, reinicie o sender.

> Corolário que me enganou em 31/08: **uma sonda de fora não distingue "sender
> morto" de "sender ocupado servindo o OBS"**. Eu conectei um
> `srt-live-transmit` do Mac, não entrei, e concluí que não havia ninguém
> escutando — havia, e estava entregando para o OBS o tempo todo. Se precisar
> testar por fora, use **outra porta** e um segundo `send`, ou pare o OBS antes.

**Fullscreen exclusivo derruba a captura.** `DXGI_ERROR_ACCESS_LOST` em ~4 s. O
jogo tem que estar em **borderless** (`proximos-testes.md` §F2.3-bis).

**Quando as duas pontas discordam, vale a que tem o log.** Já erramos duas vezes
inferindo causa no emissor a partir de sintoma no receptor. O console do `send`
tem a resposta; o `ENDED` do OBS não tem.

**Não escreva nada no `[audio] offset_ms` sem medir.** O sender já foi medido e
está alinhado em 21 ms, antes e depois do SRT (`fase3.md` §8). O que soou 2–3 s
atrasado era o caminho de **monitoração** do OBS, que nem entra na gravação
(`fase3.md` §9).

**Nada mais pode estar tocando durante o F3.4.** Ver §2.

## 5. Sintoma → onde olhar

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| o `send` sobe e morre em ~4 s | `DXGI_ERROR_ACCESS_LOST` — fullscreen exclusivo | borderless |
| o `send` nem sobe, com áudio ligado | o device dshow | `lanstream send --no-audio`: se funcionar, é o áudio e só ele — o comando sem áudio é **byte a byte** o da Fase 2 |
| `Address already in use` | ffmpeg órfão | `Get-Process ffmpeg | Stop-Process` |
| o doctor diz que o `host` não é desta máquina | o DHCP trocou o IP, ou o toml é anterior ao 010d763 | a mensagem do doctor lista as duas hipóteses |
| `doctor --audio` não lista nada | nenhum device de captura | `fase3.md` §1 tem a ordem de tentativa |
| device listado como `loopback` mas o Mac não ouve nada | Stereo Mix da placa errada | mede-se com `volumedetect`: `fase3.md` §1 |
| o Mac não recebe imagem | quase sempre o sender morreu | as últimas linhas do console do `send` |

## 6. A config desta máquina, para conferência

```toml
[network]
host = "192.168.0.12"   # esta máquina, o sender
peer = "192.168.0.21"   # o Mac
port = 9000

[audio]
enabled = true
device  = "virtual-audio-capturer"
```

O `lanstream.toml` é ignorado pelo git de propósito: cada máquina tem o seu. Se a
porta mudar para um teste, **devolva o 9000 depois** — o OBS do Mac aponta para lá.
