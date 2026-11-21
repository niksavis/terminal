$ErrorActionPreference = "Continue"
$Usage = "usage: terminal <status|update> [--wsl|--win] [--pinned]"
$Cmd = ""
$Target = "all"
$Pinned = $false
foreach ($arg in $args) {
  if ($arg -in "status", "update") { $Cmd = $arg }
  elseif ($arg -match '^--?(wsl|win)$') { $Target = $Matches[1] }
  elseif ($arg -match '^--?pinned$') { $Pinned = $true }
  else { Write-Host "terminal: unknown argument '$arg'"; Write-Host $Usage; exit 2 }
}
if (-not $Cmd -or ($Pinned -and $Cmd -ne "update")) { Write-Host $Usage; exit 2 }

$H = $env:USERPROFILE
$Failed = $false
$InstalledRef = "__SETUP_REF__"
$Releases = "__RELEASES__"
$TagPattern = '^v\d+\.\d+\.\d+$'

function Find-Uvx {
  $found = Get-Command uvx -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($found) { return $found.Source }
  $local = Join-Path $H ".local\bin\uvx.exe"
  if (Test-Path $local) { return $local }
  return $null
}

function Target-Ref {
  if ($Pinned) { return $InstalledRef }
  $location = $null
  try {
    $r = Invoke-WebRequest -Method Head -MaximumRedirection 0 -TimeoutSec 15 -UseBasicParsing -ErrorAction Stop "$Releases/latest"
    $location = $r.Headers.Location
  } catch {
    $response = $_.Exception.Response
    if ($response) {
      $location = $response.Headers.Location
      if (-not $location) { try { $location = $response.Headers["Location"] } catch {} }
    }
  }
  $tag = ("$location" -split '/')[-1]
  if ($tag -match $TagPattern) { return $tag }
  return $null
}

function Update-Here {
  $target = Target-Ref
  if (-not $target) {
    Write-Host "!! the latest terminal release could not be read from $Releases/latest, so terminal does not update. To update with the installed release, run: terminal update --pinned"
    return $false
  }
  Write-Host "setup: installed $InstalledRef, target $target"
  $ok = $true
  $env:TERMINAL_SETUP_REF = $target
  try {
    if ($target -match $TagPattern) {
      & { Invoke-RestMethod "$Releases/download/$target/install.ps1" | Invoke-Expression }
    } else {
      $uvx = Find-Uvx
      if (-not $uvx) { throw "uvx is not on the PATH" }
      & $uvx --python 3.14 --refresh-package terminal --from "__SETUP_SOURCE__" terminal-setup
      if ($LASTEXITCODE -ne 0) { throw "exit code $LASTEXITCODE" }
    }
  } catch {
    Write-Host "!! the setup run of $target failed: $($_.Exception.Message)"
    $ok = $false
  }
  $agents = Join-Path $H ".local\bin\agents.ps1"
  if (Test-Path $agents) {
    $env:AGENTS_NESTED = "1"
    $side = @()
    if ($Target -eq "win") { $side = @("--win") }
    & $agents update @side
    if ($LASTEXITCODE -ne 0) { Write-Host "!! agents update failed"; $ok = $false }
    Remove-Item Env:AGENTS_NESTED -ErrorAction SilentlyContinue
  }
  return $ok
}

if ($Cmd -eq "update") {
  if ($Target -eq "wsl") {
    & wsl.exe --exec bash -c 'p=~/.local/bin/terminal; test -x $p || { echo terminal is not in WSL, so terminal skips WSL. To add it, run the terminal setup.; exit 0; }; exec $p $@' terminal update --wsl @(if ($Pinned) { "--pinned" })
    if ($LASTEXITCODE -ne 0) { exit 1 }
    exit 0
  }
  if (-not (Update-Here)) { exit 1 }
  exit 0
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