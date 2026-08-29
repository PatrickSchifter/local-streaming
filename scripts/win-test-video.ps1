# Fase 0 / Teste 1 - envia SO VIDEO do Windows via SRT.
# Uso:  powershell -ExecutionPolicy Bypass -File win-test-video.ps1 [-Gpu nvidia|amd|intel|cpu] [-Fps 60] [-Bitrate 30M] [-Port 9000]
# Deixe rodando; no Mac rode  ./scripts/mac-preview.sh <IP-DO-WINDOWS>
# Ctrl+C encerra.

param(
  [ValidateSet('nvidia','amd','intel','cpu')][string]$Gpu = 'nvidia',
  [int]$Fps = 60,
  [string]$Bitrate = '30M',
  [int]$Port = 9000,
  [int]$Monitor = 0
)

# ddagrab entrega frames D3D11 na GPU. Cada encoder quer um formato diferente:
#  - NVENC precisa que os frames sejam mapeados pra CUDA e convertidos pra nv12
#  - AMF/QSV consomem D3D11 direto
#  - CPU exige baixar os frames pra RAM (custa caro, so pra diagnostico)
switch ($Gpu) {
  'nvidia' { $filter = "ddagrab=$($Monitor):framerate=$Fps,hwmap=derive_device=cuda,scale_cuda=format=nv12"
             $venc   = @('-c:v','h264_nvenc','-preset','p5','-tune','hq','-rc','cbr') }
  'amd'    { $filter = "ddagrab=$($Monitor):framerate=$Fps"
             $venc   = @('-c:v','h264_amf','-quality','quality','-rc','cbr') }
  'intel'  { $filter = "ddagrab=$($Monitor):framerate=$Fps"
             $venc   = @('-c:v','h264_qsv','-preset','medium') }
  'cpu'    { $filter = "ddagrab=$($Monitor):framerate=$Fps,hwdownload,format=bgra,format=nv12"
             $venc   = @('-c:v','libx264','-preset','veryfast','-tune','zerolatency') }
}

$gop = $Fps * 2
$url = "srt://0.0.0.0:${Port}?mode=listener&latency=120000"

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
Write-Host "Escutando em SRT porta $Port. No Mac:  ./scripts/mac-preview.sh <IP-DESTE-PC>" -ForegroundColor Green
Write-Host ""
& ffmpeg @args
