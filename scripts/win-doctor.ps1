# Fase 0 - diagnostico do lado Windows
# Uso:  powershell -ExecutionPolicy Bypass -File win-doctor.ps1
# Cole a saida inteira de volta no chat.

$ErrorActionPreference = "Continue"
function Sec($t) { Write-Host ""; Write-Host "=== $t ===" -ForegroundColor Cyan }

Sec "SO"
(Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, OSArchitecture | Format-List | Out-String).Trim()

Sec "GPU"
Get-CimInstance Win32_VideoController |
  Select-Object Name, DriverVersion, @{n='VRAM_MB';e={[math]::Round($_.AdapterRAM/1MB)}},
                CurrentHorizontalResolution, CurrentVerticalResolution, CurrentRefreshRate |
  Format-List | Out-String

Sec "CPU / RAM"
(Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores | Format-List | Out-String).Trim()
"RAM_GB: " + [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB, 1)

Sec "REDE"
Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object { $_.IPAddress -notlike '169.254.*' -and $_.IPAddress -ne '127.0.0.1' } |
  Select-Object IPAddress, InterfaceAlias, PrefixLength | Format-Table -Auto | Out-String
Get-NetAdapter | Where-Object Status -eq 'Up' |
  Select-Object Name, InterfaceDescription, LinkSpeed | Format-Table -Auto | Out-String

Sec "FFMPEG"
$ff = Get-Command ffmpeg -ErrorAction SilentlyContinue
if (-not $ff) {
  Write-Host "FFMPEG NAO ENCONTRADO NO PATH" -ForegroundColor Red
  Write-Host "Instale:  winget install --id=Gyan.FFmpeg -e"
  Write-Host "(feche e reabra o terminal depois, pro PATH atualizar)"
} else {
  Write-Host "path: $($ff.Source)"
  (ffmpeg -hide_banner -version 2>&1 | Select-Object -First 2) -join "`n"

  Sec "  encoders de hardware"
  $enc = ffmpeg -hide_banner -encoders 2>&1 | Select-String -Pattern 'nvenc|_amf|_qsv'
  if ($enc) { $enc | ForEach-Object { $_.Line } } else { Write-Host "NENHUM encoder de hardware" -ForegroundColor Red }

  Sec "  ddagrab (captura de tela na GPU)"
  $dda = ffmpeg -hide_banner -filters 2>&1 | Select-String -Pattern 'ddagrab'
  if ($dda) { $dda.Line } else { Write-Host "ddagrab AUSENTE - build de ffmpeg errado" -ForegroundColor Red }

  Sec "  protocolo SRT"
  $srt = ffmpeg -hide_banner -protocols 2>&1 | Select-String -Pattern '^\s*srt\s*$'
  if ($srt) { "srt OK" } else { Write-Host "SRT AUSENTE - use o build full (gyan.dev/BtbN), nao o essentials" -ForegroundColor Red }

  Sec "  devices de audio DirectShow"
  Write-Host "(procure por 'CABLE Output' ou 'virtual-audio-capturer'; se nao houver nenhum, e a Fase 3)"
  ffmpeg -hide_banner -list_devices true -f dshow -i dummy 2>&1 | Select-String -Pattern 'DirectShow audio|"' | ForEach-Object { $_.Line }
}

Sec "FIREWALL - regra da porta 9000/UDP"
$rule = Get-NetFirewallRule -DisplayName "lanstream SRT" -ErrorAction SilentlyContinue
if ($rule) { "JA EXISTE (enabled=$($rule.Enabled))" }
else {
  Write-Host "AUSENTE. Rode uma vez num PowerShell COMO ADMINISTRADOR:" -ForegroundColor Yellow
  Write-Host '  New-NetFirewallRule -DisplayName "lanstream SRT" -Direction Inbound -Protocol UDP -LocalPort 9000 -Action Allow -Profile Private'
}

Sec "FIM"
