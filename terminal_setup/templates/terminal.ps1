$ErrorActionPreference = "Continue"
$Usage = "usage: terminal status [--wsl|--win]"
$Cmd = ""
$Target = "all"
foreach ($arg in $args) {
  if ($arg -eq "status") { $Cmd = $arg }
  elseif ($arg -match '^--?(wsl|win)$') { $Target = $Matches[1] }
  else { Write-Host "terminal: unknown argument '$arg'"; Write-Host $Usage; exit 2 }
}
if (-not $Cmd) { Write-Host $Usage; exit 2 }

$H = $env:USERPROFILE
$Failed = $false

function Find-Uvx {
  $found = Get-Command uvx -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($found) { return $found.Source }
  $local = Join-Path $H ".local\bin\uvx.exe"
  if (Test-Path $local) { return $local }
  return $null
}

if ($Target -ne "wsl") {
  $uvx = Find-Uvx
  if (-not $uvx) {
    Write-Host "!! uvx is not on the PATH, so terminal cannot read the tool versions. Run the terminal setup again to install uv."
    $Failed = $true
  } else {
    $env:TERMINAL_STATUS_SIDE = "windows"
    & $uvx --from "__SETUP_SOURCE__" terminal-setup --only status
    if ($LASTEXITCODE -ne 0) { $Failed = $true }
    Remove-Item Env:TERMINAL_STATUS_SIDE -ErrorAction SilentlyContinue
  }
  $agents = Join-Path $H ".local\bin\agents.ps1"
  if (Test-Path $agents) {
    $env:AGENTS_NESTED = "1"
    & $agents status --win
    if ($LASTEXITCODE -ne 0) { $Failed = $true }
    Remove-Item Env:AGENTS_NESTED -ErrorAction SilentlyContinue
  }
}

if ($Target -ne "win") {
  if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    "WSL: wsl.exe is not on the PATH, so terminal skips WSL."
  } else {
    & wsl.exe --exec bash -c 'p=~/.local/bin/terminal; test -x $p || { echo terminal is not in WSL, so terminal skips WSL. To add it, run the terminal setup.; exit 0; }; exec $p $@' terminal $Cmd --wsl
    if ($LASTEXITCODE -ne 0) { $Failed = $true }
  }
}

if ($Failed) { exit 1 }
exit 0
