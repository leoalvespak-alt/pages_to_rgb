param(
    [string]$Distro = "Ubuntu"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $repoRoot ".env"

if (-not (Test-Path -LiteralPath $envPath)) {
    throw "Arquivo .env não encontrado. Crie-o a partir de .env.example antes de continuar."
}

$wslIpOutput = (wsl.exe -d $Distro -- hostname -I).ToString().Trim()
$wslIps = @($wslIpOutput -split "\s+" | Where-Object {
    $_ -match "^(\d{1,3}\.){3}\d{1,3}$"
})

if ($wslIps.Count -eq 0) {
    throw "Não foi possível descobrir o IP da distribuição WSL '$Distro'."
}

$wslIp = $wslIps[0]
$content = Get-Content -LiteralPath $envPath -Raw
$databasePattern = '(?m)^DATABASE_URL=.*$'
$databaseValue = "DATABASE_URL=postgresql+asyncpg://pages_to_audio:pages_to_audio_dev@$wslIp`:5432/pages_to_audio"
$temporalPattern = '(?m)^TEMPORAL_ADDRESS=.*$'
$temporalValue = "TEMPORAL_ADDRESS=$wslIp`:7233"

if ($content -notmatch $databasePattern) {
    $content = $content.TrimEnd() + [Environment]::NewLine + $databaseValue + [Environment]::NewLine
} else {
    $content = [regex]::Replace($content, $databasePattern, $databaseValue)
}

if ($content -notmatch $temporalPattern) {
    $content = $content.TrimEnd() + [Environment]::NewLine + $temporalValue + [Environment]::NewLine
} else {
    $content = [regex]::Replace($content, $temporalPattern, $temporalValue)
}

Set-Content -LiteralPath $envPath -Value $content -NoNewline
Write-Host "DATABASE_URL atualizado para PostgreSQL WSL em $wslIp`:5432."
Write-Host "TEMPORAL_ADDRESS atualizado para Temporal WSL em $wslIp`:7233."
