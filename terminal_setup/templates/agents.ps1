$ErrorActionPreference = "Continue"
$Usage = "usage: agents <status|update|install|uninstall> [--wsl|--win] [--force]"
$Cmd = "update"
$Target = "all"
$Force = $false
foreach ($arg in $args) {
  if ($arg -match '^(status|update|install|uninstall)$') { $Cmd = $arg }
  elseif ($arg -match '^--?(wsl|win)$') { $Target = $Matches[1] }
  elseif ($arg -match '^(--?force|-f)$') { $Force = $true }
  else { Write-Host "agents: unknown argument '$arg'"; Write-Host $Usage; exit 2 }
}

$H = $env:USERPROFILE
$CodexDir = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $H ".codex" }
$Names = "claude", "codex", "daemon", "copilot"
$Label = @{ claude = "Claude Code"; codex = "Codex"; daemon = "Codex daemon"; copilot = "Copilot CLI" }
$NpmPackage = @{ claude = "__NPM_CLAUDE__"; codex = "__NPM_CODEX__"; copilot = "__NPM_COPILOT__" }
$script:Failed = @()
$script:NpmRoots = $null
$Nested = [bool]$env:AGENTS_NESTED

function Say($m) { Write-Host ""; Write-Host "==> $m" -ForegroundColor Cyan }
function SemVer($s) { if ("$s" -match '\d+\.\d+\.\d+(-(alpha|beta|rc)(\.\d+)*)?') { $Matches[0] } else { "" } }
function Step($name, [scriptblock]$block) {
  Say $name
  $global:LASTEXITCODE = 0
  try { & $block } catch { Write-Host $_ -ForegroundColor Red; $global:LASTEXITCODE = 1 }
  if ($LASTEXITCODE -ne 0) { Write-Host "!! $name failed" -ForegroundColor Red; $script:Failed += $name }
}

function Locate($c) {
  $found = Get-Command $c -CommandType Application, ExternalScript -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($found) { return $found.Source }
  $places = @(Join-Path $H ".local\bin\$c.exe")
  if ($env:LOCALAPPDATA) { $places += Join-Path $env:LOCALAPPDATA "Programs\OpenAI\Codex\bin\$c.exe" }
  foreach ($p in $places) { if (Test-Path $p) { return $p } }
  return $null
}
function Has($c) { [bool](Locate $c) }

function NpmRoots {
  if ($null -eq $script:NpmRoots) {
    $script:NpmRoots = @()
    if (Get-Command npm -ErrorAction SilentlyContinue) {
      $script:NpmRoots = @((npm prefix -g 2>$null), (npm root -g 2>$null)) | Where-Object { $_ }
    }
  }
  return $script:NpmRoots
}
function Origin($c) {
  $p = Locate $c
  if (-not $p) { return "missing" }
  $full = [IO.Path]::GetFullPath($p)
  if ($full -match '[\\/]node_modules[\\/]') { return "npm" }
  foreach ($root in (NpmRoots)) {
    $prefix = [IO.Path]::GetFullPath("$root").TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    if ($full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { return "npm" }
  }
  return "native"
}
function Refuse($n, $verb) {
  $fix = if ($verb -eq "uninstall") { "npm uninstall -g $($NpmPackage[$n])" } else { "npm install -g $($NpmPackage[$n])@latest" }
  Write-Host "!! $($Label[$n]) is an npm install, so agents does not $verb it. Run: $fix" -ForegroundColor Red
  $global:LASTEXITCODE = 1
}

function Cur($c) {
  $p = Locate $c
  if ($p) { SemVer ((& $p --version 2>$null) | Select-Object -First 1) } else { "" }
}
function Cur-Daemon {
  $d = Get-Item (Join-Path $CodexDir "packages\app-server-daemon\current") -ErrorAction SilentlyContinue
  if ($d -and $d.Target) { SemVer (Split-Path -Leaf "$($d.Target)") } else { "" }
}

function Latest-Claude {
  $channel = "latest"
  try {
    $settings = Get-Content (Join-Path $H ".claude\settings.json") -Raw -ErrorAction Stop | ConvertFrom-Json
    if ($settings.autoUpdatesChannel -in "stable", "latest") { $channel = $settings.autoUpdatesChannel }
  } catch {}
  try { SemVer (Invoke-RestMethod -TimeoutSec 15 -UseBasicParsing "__CLAUDE_LATEST_URL__/$channel") } catch { "" }
}
function Latest-Codex {
  try { SemVer (Invoke-RestMethod -TimeoutSec 15 -UseBasicParsing "__CODEX_LATEST_URL__").tag_name } catch { "" }
}
function Latest-Copilot {
  $location = $null
  try {
    $r = Invoke-WebRequest -Method Head -MaximumRedirection 0 -TimeoutSec 15 -UseBasicParsing -ErrorAction Stop "__COPILOT_LATEST_URL__"
    $location = $r.Headers.Location
  } catch {
    $response = $_.Exception.Response
    if ($response) {
      $location = $response.Headers.Location
      if (-not $location) { try { $location = $response.Headers["Location"] } catch {} }
    }
  }
  SemVer "$location"
}

function ToVer($v) { [version]($v -replace '-.*$', '') }
function State($installed, $latest) {
  if (-not $installed) { "missing" }
  elseif (-not $latest) { "unknown" }
  elseif ($installed -eq $latest -or (ToVer $installed) -ge (ToVer $latest)) { "ok" }
  else { "update" }
}

$script:Cur = @{}
$script:New = @{}
$script:St = @{}
$script:Origin = @{}
function Check-All {
  $script:New.claude = Latest-Claude
  $script:New.codex = Latest-Codex
  $script:New.copilot = Latest-Copilot
  $script:New.daemon = $script:New.codex
  $script:Cur.claude = Cur claude
  $script:Cur.codex = Cur codex
  $script:Cur.copilot = Cur copilot
  $script:Cur.daemon = Cur-Daemon
  $script:Origin.claude = Origin claude
  $script:Origin.codex = Origin codex
  $script:Origin.copilot = Origin copilot
  $script:Origin.daemon = "native"
  foreach ($n in $Names) {
    if ($script:Origin[$n] -eq "npm" -and $n -ne "copilot") { $script:St[$n] = "npm" }
    else { $script:St[$n] = State $script:Cur[$n] $script:New[$n] }
  }
}
function Print-Table {
  "{0,-8} {1,-12} {2,-12} {3}" -f "agent", "installed", "latest", "state" | Write-Host
  foreach ($n in $Names) {
    $color = switch ($script:St[$n]) { "ok" { "Green" } "unknown" { "Red" } default { "Yellow" } }
    $c = if ($script:Cur[$n]) { $script:Cur[$n] } else { "-" }
    $l = if ($script:New[$n]) { $script:New[$n] } else { "?" }
    Write-Host ("{0,-8} {1,-12} {2,-12} " -f $n, $c, $l) -NoNewline
    Write-Host $script:St[$n] -ForegroundColor $color
  }
}
function Needs($n) { $Force -or $script:St[$n] -ne "ok" }

function Install-Claude { __CLAUDE_INSTALL_PS1__ }
function Install-Codex { $env:CODEX_NON_INTERACTIVE = "1"; __CODEX_INSTALL_PS1__ }
function Install-Copilot {
  if (Get-Command npm -ErrorAction SilentlyContinue) { npm install -g $NpmPackage.copilot }
  else { winget install --id GitHub.Copilot -e --accept-source-agreements --accept-package-agreements }
}

function Update-Agent($n) {
  $how = Origin $n
  if ($how -eq "missing") {
    switch ($n) { "claude" { Install-Claude } "codex" { Install-Codex } "copilot" { Install-Copilot } }
  } elseif ($how -eq "npm" -and $n -eq "copilot") {
    npm install -g "$($NpmPackage.copilot)@latest"
  } elseif ($how -eq "npm") {
    Refuse $n "update"
  } else {
    & (Locate $n) update
  }
}
function Update-Daemon {
  Write-Host "Note: this restarts the Codex daemon and stops running Codex work." -ForegroundColor Yellow
  $codex = Locate codex
  if ($codex) {
    & $codex app-server daemon update
    if ($LASTEXITCODE -eq 0) { return }
    Write-Host "The daemon updater could not start, so agents uses the daemon-only installer." -ForegroundColor Yellow
  }
  $env:CODEX_INSTALL_DAEMON_ONLY = "1"
  $env:CODEX_NON_INTERACTIVE = "1"
  $global:LASTEXITCODE = 0
  try { __CODEX_INSTALL_PS1__ }
  finally { Remove-Item Env:CODEX_INSTALL_DAEMON_ONLY -ErrorAction SilentlyContinue }
}

function Uninstall-Claude {
  Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $H ".local\bin\claude.exe")
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $H ".local\share\claude")
  $global:LASTEXITCODE = 0
}
function Uninstall-Codex {
  $codex = Locate codex
  if ($codex) { & $codex app-server daemon stop *> $null }
  $paths = @(Join-Path $CodexDir "packages")
  if ($env:LOCALAPPDATA) { $paths += Join-Path $env:LOCALAPPDATA "Programs\OpenAI\Codex" }
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $paths
  $global:LASTEXITCODE = 0
}
function Uninstall-Copilot {
  if ((Origin copilot) -eq "npm") { npm uninstall -g $NpmPackage.copilot; return }
  if (Get-Command winget -ErrorAction SilentlyContinue) {
    winget list --id GitHub.Copilot -e --accept-source-agreements *> $null
    if ($LASTEXITCODE -eq 0) { winget uninstall --id GitHub.Copilot -e; return }
  }
  "Copilot CLI is not an npm or winget install, so agents leaves it."
  $global:LASTEXITCODE = 0
}
function Uninstall-Agent($n) {
  if ($n -ne "copilot" -and (Origin $n) -eq "npm") { Refuse $n "uninstall"; return }
  switch ($n) { "claude" { Uninstall-Claude } "codex" { Uninstall-Codex } "copilot" { Uninstall-Copilot } }
}

function Maybe($n, [scriptblock]$block) {
  $title = "$($Label[$n]) (Windows)"
  if (Needs $n) { Step $title $block } else { Say $title; "up to date ($($script:Cur[$n]))" }
}

function Run-Windows {
  switch ($Cmd) {
    "status" { Check-All; Say "Windows"; Print-Table }
    "update" {
      Check-All; Say "Windows"; Print-Table
      Maybe claude { Update-Agent claude }
      Maybe codex { Update-Agent codex }
      Maybe daemon { Update-Daemon }
      Maybe copilot { Update-Agent copilot }
    }
    "install" {
      foreach ($n in "claude", "codex", "copilot") {
        $how = Origin $n
        $title = "$($Label[$n]) (Windows)"
        if ($how -eq "npm" -and $n -ne "copilot") { Step $title { Refuse $n "install" } }
        elseif ($Force -or $how -eq "missing") {
          switch ($n) { "claude" { Step $title { Install-Claude } } "codex" { Step $title { Install-Codex } } "copilot" { Step $title { Install-Copilot } } }
        }
        else { Say $title; "already installed" }
      }
    }
    "uninstall" {
      foreach ($n in "claude", "codex", "copilot") { Step "$($Label[$n]) (Windows)" { Uninstall-Agent $n } }
    }
  }
}

function Run-Wsl {
  if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) { "WSL: wsl.exe is not on the PATH, so agents skips WSL."; return }
  $forward = @($Cmd, "--wsl")
  if ($Force) { $forward += "--force" }
  $env:AGENTS_NESTED = "1"
  $env:WSLENV = if ($env:WSLENV) { "AGENTS_CONFIRMED:AGENTS_NESTED:$($env:WSLENV)" } else { "AGENTS_CONFIRMED:AGENTS_NESTED" }
  & wsl.exe --exec bash -c 'p=~/.local/bin/agents; test -x $p || { echo agents is not in WSL, so agents skips WSL. To add it, run the terminal setup with --agents all.; exit 0; }; exec $p $@' agents @forward
  if ($LASTEXITCODE -ne 0) { $script:Failed += "WSL" }
}

if ($Cmd -eq "uninstall" -and -not $env:AGENTS_CONFIRMED) {
  if ((Read-Host "Uninstall Claude Code, Codex and Copilot CLI ($Target)? The configuration is kept. Type yes") -ne "yes") { "Cancelled."; exit 1 }
  $env:AGENTS_CONFIRMED = "1"
}

if ($Target -ne "wsl") { Run-Windows }
if ($Target -ne "win") { Run-Wsl }

if ($script:Failed.Count) { Write-Host ""; Write-Host "Failed: $($script:Failed -join ', ')" -ForegroundColor Red; exit 1 }
if (-not $Nested) {
  Write-Host ""
  Write-Host "All done." -ForegroundColor Green
}
exit 0
