# Fase 1 — Esqueleto e diagnóstico

O que a Fase 0 descobriu na mão, a Fase 1 precisa descobrir sozinha. Este
documento registra a validação do `lanstream doctor` — o único critério de saída
da fase.

Data: 2026-08-29

---

## 1. ✅ F1 — `lanstream doctor` no Windows. A Fase 1 fecha.

O teste não mede rede nem qualidade: mede se o diagnóstico automático **concorda
com o que a Fase 0 provou pelo caminho difícil**. Rodou em segundos, sem precisar
do Mac do outro lado.

O lado do Mac já tinha sido validado quando o código foi escrito. Faltava a
rodada real no Windows: até aqui o ramo Windows tinha sido executado à força, mas
contra um ffmpeg de Mac — prova que não quebra, não que acerta.

### Ambiente

| Item | Valor |
|---|---|
| SO | Windows 10 Pro 19045, papel detectado: `sender (Windows)` |
| Python | 3.13.15 (`requires-python = ">=3.11"`) |
| Instalação | `uv venv && uv pip install -e ".[dev]"` — 10 pacotes, ~1 s |
| `uv` | já instalado (WinGet), o `winget install` não foi necessário |
| Versão | `lanstream 0.1.0` |

A instalação rodou de primeira, sem ajuste manual. É o primeiro comando do
projeto executado no Windows a partir do código, e não de um `.ps1`.

### Saída integral

```
=== SISTEMA ===
  Windows-10-10.0.19045-SP0
  Python 3.13.15 — papel: sender (Windows)
  config: C:\Users\schif\Projetos\local-streaming\lanstream.toml

=== VÍDEO ===
  1920x1080@60  hevc 15M CBR  gop=120  monitor=0
  SRT buffer: 1200 ms

=== CHECAGENS ===
[ OK  ] ffmpeg: 8.1 (full_build-www.gyan.dev)
        C:\Users\schif\AppData\Local\Microsoft\WinGet\Links\ffmpeg.EXE
[ OK  ] encoders de hardware: av1_amf, av1_nvenc, av1_qsv, h264_amf, h264_nvenc,
        h264_qsv, hevc_amf, hevc_nvenc, hevc_qsv, mjpeg_qsv, mpeg2_qsv, vp9_qsv
[ OK  ] encoder escolhido: hevc_nvenc
[ OK  ] ddagrab (captura na GPU): presente
[ OK  ] protocolo SRT no ffmpeg: presente
[ OK  ] firewall: regra "lanstream SRT" existe
[ OK  ] IPs locais: 192.168.0.12
[ OK  ] porta 9000/UDP: livre para o sender
[ OK  ] alcance até 192.168.0.21: responde ao ping

=== URLs ===
  sender (Windows):  srt://0.0.0.0:9000?mode=listener&latency=1200000
  OBS / ffmpeg:      srt://192.168.0.21:9000?mode=caller&latency=1200000
  srt-live-transmit: srt://192.168.0.21:9000?mode=caller&latency=1200
  (o latency muda de unidade entre os dois — µs no OBS, ms no slt)

Tudo certo deste lado.
```

Código de saída **0**. Nenhuma FALHA, nenhum AVISO.

### Linha por linha, contra o que a Fase 0 exige

| Linha | Esperado | Obtido | |
|---|---|---|---|
| `ffmpeg` | 8.1 | **8.1** `full_build-www.gyan.dev` | ✅ o `winget upgrade` não reintroduziu o bug de NVENC do §2 |
| `encoders de hardware` | inclui `hevc_nvenc` | 12 encoders, `hevc_nvenc` entre eles | ✅ build correto |
| `encoder escolhido` | `hevc_nvenc` | `hevc_nvenc` | ✅ topo da cadeia de fallback, sem degradar |
| `ddagrab` | presente | presente | ✅ é build `full`, não `essentials` |
| `protocolo SRT` | presente | presente | ✅ |
| `firewall` | regra existe | existe | ✅ a regra da Fase 0 sobreviveu |
| `porta 9000/UDP` | livre | livre | ✅ sem ffmpeg órfão da Fase 0 segurando a porta |
| `IPs locais` | inclui 192.168.0.12 | `192.168.0.12` | ✅ **o IP não mudou** — o `[network] host` do Mac segue válido |
| `alcance` | precisa de host | responde ao ping | ✅ |

Nove de nove. O diagnóstico automático reproduz, em segundos, o levantamento que
a Fase 0 levou dois dias para montar.

Vale registrar o que **não** apareceu: o `[ AVISO ]` de porta ocupada. O doctor
classifica porta 9000 tomada como aviso e não como falha, justamente para ser
seguro de rodar com o sender no ar — mas não havia sender no ar, e a porta estava
mesmo livre. O caminho do aviso segue sem exercício real.

### 🟡 Achado — `[network] host` tem dois donos, e eles discordam

O `docs/proximos-testes.md` mandava criar um `lanstream.toml` com
`host = "192.168.0.21"` (o **Mac**) para exercitar a linha de alcance. Funciona:
a checagem de alcance passa a medir a outra ponta de verdade. Mas o mesmo campo
alimenta o bloco de URLs, e aí ele quer dizer outra coisa:

- `lanstream.example.toml` e a mensagem de aviso do próprio doctor
  (`doctor.py:365`) definem `host` como o **IP do Windows** — "é o que o Mac usa
  para conectar".
- O bloco de URLs monta a URL de caller a partir dele (`doctor.py:422`).

Com `host` apontando para o Mac, a URL impressa fica **errada**: manda o OBS
conectar em `192.168.0.21`, que é o próprio Mac, e não no listener que está em
`192.168.0.12`.

Confirmado rodando de novo com `host = "192.168.0.12"`:

```
[ OK  ] alcance até 192.168.0.12: responde ao ping
  OBS / ffmpeg:      srt://192.168.0.12:9000?mode=caller&latency=1200000
```

Agora as URLs saem certas — mas o alcance virou um ping em si mesmo, que passa de
graça e não prova nada.

**Um campo, dois significados incompatíveis.** No lado do Windows não existe valor
que sirva aos dois: ou o alcance mede a outra ponta, ou as URLs saem corretas.
Do lado do Mac o conflito não aparece, porque lá as duas leituras coincidem — o
sender *é* a outra ponta. Foi por isso que passou despercebido.

**Não é bloqueante para a Fase 1:** as nove checagens que o critério de saída pede
passaram, e a linha de alcance faz o que promete. Mas a Fase 2 vai gerar essa URL
para valer, e aí o ambíguo vira defeito.

**Encaminhamento:** separar em dois campos — `host` continua sendo o sender (o que
as URLs precisam) e um novo `peer` aponta para a outra ponta (o que o alcance
precisa). Cada lado preenche o do outro. Enquanto isso não existe, o
`lanstream.toml` do Windows deve ter `host = "192.168.0.12"`, que é o significado
documentado; a linha de alcance fica sem valor nessa máquina.

### O que isto fecha

- ✅ **Critério de saída da Fase 1 batido:** o `doctor` roda nos dois SOs e o
  diagnóstico está correto nos dois.
- ✅ O `doctor` serve de preflight da Fase 2: sai **1** em caso de FALHA, então dá
  para encadear antes de subir o sender.
- ✅ O ambiente do Windows continua exatamente como a Fase 0 o deixou — mesma
  versão de ffmpeg, mesmo IP, mesma regra de firewall.
- 🟡 Aberto: a ambiguidade do `[network] host`, acima. Resolver na Fase 2.
- 🟡 Sem exercício: o ramo de AVISO da porta ocupada. Sai de graça na Fase 2, na
  primeira vez que o doctor rodar com o sender no ar.
