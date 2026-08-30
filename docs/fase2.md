# Fase 2 — Sender de vídeo (Windows)

O que a Fase 0 rodou colando comando na mão, a Fase 2 monta a partir da config.
Este documento registra o que foi construído, o que foi verificado e **o que
ainda não foi** — o critério de saída da fase depende de uma máquina que não é
esta.

Data: 2026-08-29

---

## 1. O comando montado é o mesmo que a Fase 0 validou

O teste que importa não é "o código roda", é "o código monta o comando que já
sabemos que funciona". O `send --dry-run` imprime:

```
ffmpeg -hide_banner -loglevel info -stats -nostdin -init_hw_device d3d11va \
  -filter_complex ddagrab=0:framerate=60 \
  -c:v hevc_nvenc -preset p5 -tune hq -rc cbr \
  -b:v 15M -maxrate 15M -bufsize 15M -g 120 -bf 0 \
  -f mpegts "srt://0.0.0.0:9000?mode=listener&latency=1200000"
```

Contra o `scripts/win-test-video.ps1` (ramo `nvidia`, que é o único testado numa
GPU de verdade) a diferença é **uma flag**: `-nostdin`. Ela entra porque agora há
um supervisor Python no meio — sem ela o ffmpeg disputa o teclado do console com
quem o supervisiona, e o Ctrl+C fica ambíguo.

O resto é idêntico, inclusive a ordem, para que um `diff` entre os dois continue
legível quando algo quebrar.

### O que o argv carrega de decisão

| Trecho | Por quê |
|---|---|
| `-init_hw_device d3d11va` | O `ddagrab` precisa de um device D3D11 pronto; ele não cria o seu. |
| `ddagrab` direto no encoder | `hwmap=derive_device=cuda` dá ENOSYS e o `scale_d3d11` não configura o pad neste build (baseline §2). Sem filtro no meio dá o mesmo desempenho. |
| `-b:v = -maxrate = -bufsize` | CBR de verdade. O teto aqui é de transporte, não de qualidade (PLANO §3.3). |
| `-g 120` | Keyframe a cada 2 s, igual à Fase 0. |
| `-bf 0` | Como a Fase 0. O §3.1 permite ligar B-frames, mas isso é knob da Fase 7, com medição junto. |

## 2. `[video] preset` deixou de ter um default global

Descoberta ao escrever o `encoders.py`: **cada fabricante nomeia o preset do seu
jeito.** `-preset p5` é NVENC, `-quality quality` é AMF, `-preset medium` é QSV,
`-preset veryfast` é x264. O default anterior (`preset = "p5"`) só estava certo
porque a única máquina do projeto tem NVIDIA — em qualquer fallback ele viraria
um `-preset p5` num `libx264`, que o ffmpeg recusa, ou pior, aceita e ignora.

Agora o default é **vazio = o da família do encoder escolhido**, e um valor
explícito é conferido contra a lista da família:

```
$ lanstream send --dry-run     # com preset = "veryfast" no toml
erro: [video] preset = 'veryfast' não vale para hevc_nvenc.
  Valores da família nvenc: p1, p2, p3, p4, p5, p6, p7
  Deixe a chave vazia para usar o default (p5).
```

O `doctor` ganhou a mesma checagem. Motivo de ela existir: o ffmpeg aceita
`-preset veryfast` num `hevc_nvenc` sem reclamar e cai num default silencioso —
o sintoma seria "a qualidade mudou e eu não sei por quê", meia hora depois de ir
ao ar.

O comportamento efetivo não mudou nesta máquina: `preset = ""` com `hevc_nvenc`
resolve para `-preset p5`, exatamente o que a Fase 0 usou.

## 3. ⛔ A escala na GPU não entra — o item morreu por dois motivos independentes

O plano previa "escala opcional na GPU (`scale_cuda`/`scale_d3d11`) — jogar em
1440p e transmitir 1080p sem custo de CPU". Nenhuma linha foi escrita para isso,
de propósito:

1. **O build não consegue.** A Fase 0 já tinha medido as duas cadeias possíveis:
   `hwmap=derive_device=cuda,scale_cuda` falha com `Failed to created derived
   device context: -40` (ENOSYS) e `scale_d3d11` falha com `Failed to configure
   output pad` (baseline §2). Não é ajuste de sintaxe: este build não deriva um
   device CUDA a partir do D3D11.
2. **Não há o que escalar.** O `ddagrab` captura o que o monitor tem, e o monitor
   do Windows é 1920x1080@60. Não existe fonte 1440p para reduzir — é o mesmo
   motivo que já riscou o teste de 1440p/120fps da Fase 7.

Sobraria escalar na CPU (`hwdownload,scale,...`), que é exatamente o custo que o
item existia para evitar. Implementar seria escrever um caminho que não roda,
para um cenário que não existe, com a técnica que o item recusava.

**Consequência prática:** `[video] width`/`height` não entram no comando. São
expectativa declarada, e o `send` as imprime como tal ("monitor 0 — esperado
1920x1080") justamente para que a discordância apareça na tela se o monitor
mudar. Reavaliar só se o monitor mudar **e** um build com `scale_d3d11`
funcional aparecer.

## 4. Ctrl+C: medido, não presumido

A promessa da fase é "encerra limpo no Ctrl+C, sem ffmpeg órfão segurando a
porta". Como não dá para rodar o `ddagrab` no Mac, o supervisor foi exercitado
com uma fonte sintética (`testsrc`) e um SIGINT no **grupo de processos** — que é
o que o console faz de verdade, e não um `terminate()` no filho, que testaria
outra coisa.

```
[harness] ffmpeg filhos antes do sinal: ['48856']
...
[log ] Exiting normally, received signal 2.
RETORNO=255
[harness] saiu em 0.12s com codigo 0
[harness] ffmpeg orfaos depois: nenhum
```

Três decisões saíram desse teste:

- **O ffmpeg não vai para um grupo de processos próprio.** `CREATE_NEW_PROCESS_GROUP`
  pareceria mais limpo e seria pior: o ffmpeg não receberia o Ctrl+C e só sairia
  no `kill`, deixando o TS truncado e a porta ocupada. Herdando o grupo, ele
  recebe o sinal, fecha o mux e o socket sozinho — os 0.12 s acima.
- **O stderr continua sendo drenado durante o encerramento**, numa thread daemon.
  Não é zelo com o log: pipe cheio bloqueia quem escreve, e o ffmpeg ainda tem o
  que dizer depois do sinal. O `Exiting normally` acima só apareceu por causa
  disso. Depois vêm `terminate` e `kill`, com 5 s cada, para o caso de ele travar.
- **Saída 255 não é falha.** É como o ffmpeg reporta "recebi SIGINT e saí". O
  `send` traduz para 0, senão um script de sessão acharia que a live quebrou.

A leitura do stderr trata `\r` como fim de linha: a linha de progresso do ffmpeg
se reescreve com `\r` e nunca manda `\n`, e um `readline()` normal deixaria o
console mudo por minutos, parecendo que o sender morreu.

## 5. O que foi verificado aqui, e o que só o Windows responde

Verificado no Mac (o que não depende de GPU NVIDIA nem de `ddagrab`):

| Item | Resultado |
|---|---|
| Comando montado == o da Fase 0 | ✅ idêntico + `-nostdin` |
| Cadeia de fallback (só AMF / só software / vazia) | ✅ `hevc_amf`, `libx264`, `hevc_nvenc` |
| Override de encoder inexistente | ✅ erro de uma linha, código 2 |
| Preset fora da família | ✅ erro de uma linha, código 2 |
| `--bitrate 20M` e `codec = "h264"` | ✅ propagam para as três flags de taxa |
| Encoder de software puxa `hwdownload` | ✅ cadeia igual à do ramo `cpu` da Fase 0 |
| `send` fora do Windows | ✅ recusa com o motivo (ddagrab) e aponta o `--dry-run` |
| Ctrl+C sem órfão | ✅ 0.12 s, sem sobrevivente |
| `example.toml` == defaults (invariante da Fase 1) | ✅ mantido |
| `ruff check src/` | ✅ limpo |

**Verificado no Windows em 30/08** — quatro dos cinco passos do protocolo
(`proximos-testes.md` §F2), os que não dependem do Mac:

| Item | Resultado |
|---|---|
| `doctor`: 11 checagens | ✅ 11 OK, código 0 (`hevc_nvenc`, `-preset p5`) |
| Comando montado no Windows real | ✅ igual ao do §1, com o caminho absoluto do ffmpeg no argv[0] |
| `CTRL_C_EVENT` do console do Windows | ✅ 0.27–0.67 s, `Exiting normally, received signal 2`, sem `terminate` |
| Sem ffmpeg órfão / porta 9000 livre | ✅ nas três rodadas |
| Dois `send` seguidos | ✅ o segundo sobe na hora, sem `Address already in use` |

O ponto do §4 se confirma no SO que ele descreve: **herdar o grupo do console é o
que faz o Ctrl+C chegar no ffmpeg no Windows também.** O `CREATE_NEW_PROCESS_GROUP`
continua sendo a escolha errada, agora por medição nas duas plataformas.

**Ainda não verificado — é o que segura o critério de saída da fase**
(passo F2.3 do protocolo):

- [ ] `lanstream send` rodando no Windows, com o OBS do Mac como Media Source.
      O que falta a rodada confirmar: o `ddagrab` entregando frame **com o
      receptor conectado**, e os fps com jogo real (a Fase 0 mediu 55–58 com a
      tela em movimento e deixou o caso do fullscreen exclusivo em aberto). As
      rodadas de 30/08 foram curtas, com a tela parada e sem ninguém do outro
      lado — não medem nem fps nem bitrate, e não valem como F2.3.

## 6. Revisão de código: cinco defeitos, dois deles em promessas escritas

Um `/code-review` sobre o diff da fase achou cinco problemas reais. Vale
registrar porque dois deles eram **docstrings afirmando o oposto do que o código
fazia** — o tipo de defeito que sobrevive a leitura casual justamente porque o
comentário ao lado diz que está tudo bem.

| # | Defeito | Correção |
|---|---|---|
| 1 | `pick()` inferia "não verifiquei" de `available` vazio. Um `-encoders` devolvendo lista vazia (build esquisito, ou o formato mudando de novo) faria o doctor imprimir `encoder escolhido: hevc_nvenc` **verde** no lugar de uma FALHA. | `verified` virou parâmetro explícito. Bug de parser não vira mais diagnóstico otimista. |
| 2 | `proc.stderr.close()` corria com a thread que ainda estava dentro de um `os.read()`. Com o fd reciclado, ela leria de um arquivo qualquer e cuspiria o conteúdo no console. | O `run()` passou a ser dono da thread: `join` antes de fechar, e se o join não bastar o pipe fica aberto de propósito. |
| 3 | Duas threads escrevendo no console e no `pending` sem sincronia — no encerramento, que é o caminho que o usuário sempre vê. | Um lock no `_echo_ffmpeg`. |
| 4 | O `shell_line` promete ser colável no PowerShell, mas com o ffmpeg em `C:\Program Files\...` o argv[0] sai entre aspas, e o PowerShell lê uma linha começada por `"` como expressão. | `&` na frente quando o argv[0] está entre aspas. |
| 5 | `profile_of` mandava todo nome desconhecido para o perfil de **software**, cuja docstring dizia que ele "no máximo perde desempenho". Falso: ele carrega `-preset veryfast -tune zerolatency`, que são opções privadas do x264. Um `--encoder h264_mf` (existe nos builds do gyan.dev) abortaria com "Error setting option preset". | Perfil neutro — sem preset, sem tune, sem hwdownload. Só o prefixo `lib` cai no de software. |

O 1 e o 5 são a mesma classe de erro: **um default escolhido por parecer
conservador, sem conferir o que ele de fato faz.** "Lista vazia = não consultei"
e "não reconheço = trate como software" são as duas suposições, e as duas
falhavam para o mesmo lado — o de dizer que está tudo bem.

Os testes do §4 e do §5 foram repetidos depois das correções: Ctrl+C em 0.11 s,
sem órfão, com o `Exiting normally, received signal 2` ainda capturado (o que
prova que a drenagem continua fazendo o que precisa), e o comando montado
inalterado.
