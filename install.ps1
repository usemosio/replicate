# Install the replicate-video helper and the replicate + style-writer skills (Windows PowerShell).
#
#   irm https://raw.githubusercontent.com/usemosio/replicate/main/install.ps1 | iex
#
# Needs uv (https://docs.astral.sh/uv/) or pipx, and git. FFmpeg: winget install Gyan.FFmpeg

$ErrorActionPreference = 'Stop'
$Repo = 'https://github.com/usemosio/replicate'
$Ref = if ($env:REPLICATE_REF) { $env:REPLICATE_REF } else { 'main' }

Write-Host "Installing the replicate-video CLI ($Ref)"
if (Get-Command uv -ErrorAction SilentlyContinue) {
  uv tool install --force "git+$Repo@$Ref"
} elseif (Get-Command pipx -ErrorAction SilentlyContinue) {
  pipx install --force "git+$Repo@$Ref"
} else {
  Write-Warning 'Need uv or pipx. Install uv: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"'
  return
}

$Tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("replicate-" + [guid]::NewGuid())
git clone --quiet --depth 1 --branch $Ref $Repo $Tmp
foreach ($Dir in @("$HOME\.claude\skills", "$HOME\.agents\skills")) {
  New-Item -ItemType Directory -Force -Path $Dir | Out-Null
  foreach ($Skill in @('replicate', 'style-writer')) {
    $Target = Join-Path $Dir $Skill
    if (Test-Path $Target) { Remove-Item -Recurse -Force $Target }
    Copy-Item -Recurse (Join-Path $Tmp "skills\$Skill") $Target
  }
  Write-Host "Skills installed in $Dir"
}
Remove-Item -Recurse -Force $Tmp

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
  Write-Warning 'FFmpeg is missing: winget install Gyan.FFmpeg, then run: replicate-video doctor'
} else {
  replicate-video doctor
}
