# Fase 0 / Teste 1 - envia SO VIDEO do Windows via SRT.
# Uso:  powershell -ExecutionPolicy Bypass -File win-test-video.ps1 [-Gpu nvidia|amd|intel|cpu] [-Fps 60] [-Bitrate 30M] [-Port 9000] [-LatencyMs 120]
# Deixe rodando; no Mac rode  ./scripts/mac-preview.sh <IP-DO-WINDOWS> [porta] [latencia-ms]
# Ctrl+C encerra.
#
# -LatencyMs e o buffer do SRT. CUIDADO com a unidade: o ffmpeg conta em
# MICROssegundos e o srt-live-transmit em MILIssegundos. O script recebe ms e
# converte, entao os dois lados sao configurados com o mesmo numero.
# Os dois lados precisam do MESMO valor.

param(
  [ValidateSet('nvidia','amd','intel','cpu')][string]$Gpu = 'nvidia',
  [int]$Fps = 60,
  [string]$Bitrate = '30M',
  [int]$Port = 9000,
  [int]$Monitor = 0,
  [int]$LatencyMs = 120
)

# ddagrab entrega frames D3D11 na GPU. Cada encoder quer um formato diferente:
#  - NVENC consome os frames D3D11 direto; o ffmpeg resolve a conversao sozinho
#  - AMF/QSV consomem D3D11 direto
#  - CPU exige baixar os frames pra RAM (custa caro, so pra diagnostico)
#
# NAO use "hwmap=derive_device=cuda,scale_cuda=format=nv12" aqui. O build do
# gyan.dev nao consegue derivar um device CUDA a partir do D3D11 e falha com
# "Failed to created derived device context: -40" (ENOSYS). O mesmo vale pro
# "scale_d3d11", que nao configura o output pad. Medido na Fase 0: passar o
# ddagrab direto pro nvenc da o mesmo desempenho, sem filtro nenhum no meio.
switch ($Gpu) {
  'nvidia' { $filter = "ddagrab=$($Monitor):framerate=$Fps"
             $venc   = @('-c:v','h264_nvenc','-preset','p5','-tune','hq','-rc','cbr') }
  'amd'    { $filter = "ddagrab=$($Monitor):framerate=$Fps"
             $venc   = @('-c:v','h264_amf','-quality','quality','-rc','cbr') }
  'intel'  { $filter = "ddagrab=$($Monitor):framerate=$Fps"
             $venc   = @('-c:v','h264_qsv','-preset','medium') }
  'cpu'    { $filter = "ddagrab=$($Monitor):framerate=$Fps,hwdownload,format=bgra,format=nv12"
             $venc   = @('-c:v','libx264','-preset','veryfast','-tune','zerolatency') }
}

$gop = $Fps * 2
$latencyUs = $LatencyMs * 1000   # ffmpeg quer microssegundos
$url = "srt://0.0.0.0:${Port}?mode=listener&latency=${latencyUs}"

$args = @(
  '-hide_banner','-loglevel','info','-stats',
  '-init_hw_device','d3d11va',
  '-filter_complex', $filter
) + $venc + @(
  '-b:v', $Bitrate, '-maxrate', $Bitrate, '-bufsize', $Bitrate,
  '-g', "$gop", '-bf','0',
  '-f','mpegts', $url
)

Write-Host "Comando:" -ForegroundColor Cyan
Write-Host "  ffmpeg $($args -join ' ')"
Write-Host ""
Write-Host "Escutando em SRT porta $Port, buffer ${LatencyMs} ms." -ForegroundColor Green
Write-Host "No Mac:  ./scripts/mac-preview.sh <IP-DESTE-PC> $Port $LatencyMs" -ForegroundColor Green
Write-Host ""
& ffmpeg @args
