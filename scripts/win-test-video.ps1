# Fase 0 / Teste 1 - envia SO VIDEO do Windows via SRT.
# Uso:  powershell -ExecutionPolicy Bypass -File win-test-video.ps1 [-Gpu nvidia|amd|intel|cpu] [-Codec h264|hevc] [-Fps 60] [-Bitrate 30M] [-Port 9000] [-LatencyMs 120]
# Deixe rodando; no Mac rode  ./scripts/mac-preview.sh <IP-DO-WINDOWS> [porta] [latencia-ms]
# Ctrl+C encerra.
#
# -LatencyMs e o buffer do SRT. CUIDADO com a unidade: o ffmpeg conta em
# MICROssegundos e o srt-live-transmit em MILIssegundos. O script recebe ms e
# converte, entao os dois lados sao configurados com o mesmo numero.
# Os dois lados precisam do MESMO valor.

param(
  [ValidateSet('nvidia','amd','intel','cpu')][string]$Gpu = 'nvidia',
  [ValidateSet('h264','hevc')][string]$Codec = 'h264',
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
# O HEVC rende ~a mesma qualidade do H.264 com ~40% menos bitrate. Com o teto de
# ~16-17 Mbps medido no par 4e, e o que torna 1080p60 viavel - por isso virou
# requisito, e nao preferencia. Ambos ja foram validados no par 2.
switch ($Gpu) {
  'nvidia' { $filter = "ddagrab=$($Monitor):framerate=$Fps"
             $venc   = @('-c:v',"${Codec}_nvenc",'-preset','p5','-tune','hq','-rc','cbr') }
  'amd'    { $filter = "ddagrab=$($Monitor):framerate=$Fps"
             $venc   = @('-c:v',"${Codec}_amf",'-quality','quality','-rc','cbr') }
  'intel'  { $filter = "ddagrab=$($Monitor):framerate=$Fps"
             $venc   = @('-c:v',"${Codec}_qsv",'-preset','medium') }
  'cpu'    { $enc    = if ($Codec -eq 'hevc') { 'libx265' } else { 'libx264' }
             $filter = "ddagrab=$($Monitor):framerate=$Fps,hwdownload,format=bgra,format=nv12"
             $venc   = @('-c:v',$enc,'-preset','veryfast','-tune','zerolatency') }
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
Write-Host "Codec ${Codec}, bitrate ${Bitrate}, SRT porta $Port, buffer ${LatencyMs} ms." -ForegroundColor Green
Write-Host "No Mac:  ./scripts/mac-preview.sh <IP-DESTE-PC> $Port $LatencyMs" -ForegroundColor Green
Write-Host ""
& ffmpeg @args
