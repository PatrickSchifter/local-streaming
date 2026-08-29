#!/usr/bin/env bash
# Fase 0 / Teste 1 - recebe e mostra o stream SRT vindo do Windows.
# Uso: ./scripts/mac-preview.sh <IP-DO-WINDOWS> [porta] [latencia-ms]
#
# O ffmpeg do Homebrew NAO tem libsrt, entao usamos srt-live-transmit
# (do formula `srt`) como ponte e o ffplay so consome o MPEG-TS.
set -euo pipefail

HOST="${1:-}"
PORT="${2:-9000}"
# Buffer do SRT. ATENCAO a unidade: aqui e MILIssegundos; no ffmpeg do lado do
# Windows a mesma opcao e em MICROssegundos. Os dois lados precisam bater.
LATENCY_MS="${3:-120}"
if [[ -z "$HOST" ]]; then
  echo "uso: $0 <IP-DO-WINDOWS> [porta] [latencia-ms]" >&2
  exit 1
fi

command -v srt-live-transmit >/dev/null || { echo "faltou: brew install srt" >&2; exit 1; }
command -v ffplay            >/dev/null || { echo "faltou: brew install ffmpeg" >&2; exit 1; }

URL="srt://${HOST}:${PORT}?mode=caller&latency=${LATENCY_MS}"
echo "conectando em ${URL}"
echo "(Ctrl+C encerra; 'q' na janela do video tambem)"
echo

# -fflags nobuffer + -flags low_delay: mostra o quadro assim que chega,
# util pra medir latencia real na Fase 0. Em producao quem bufferiza e o OBS.
srt-live-transmit "$URL" file://con/ \
  | ffplay -hide_banner -loglevel info \
      -fflags nobuffer -flags low_delay -framedrop \
      -window_title "lanstream preview - ${HOST}:${PORT}" -
