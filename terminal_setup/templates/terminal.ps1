$ErrorActionPreference = "Continue"
$InstalledRef = "__SETUP_REF__"
$Releases = "__RELEASES__"
$TagPattern = '^v\d+\.\d+\.\d+$'

function Newer-Release-Hint {
  $location = $null
  try {
    $r = Invoke-WebRequest -Method Head -MaximumRedirection 0 -TimeoutSec 10 -UseBasicParsing -ErrorAction Stop "$Releases/latest"
    $location = $r.Headers.Location
  } catch {
    $response = $_.Exception.Response
    if ($response) { $location = $response.Headers.Location }
  }
  $tag = ("$location" -split '/')[-1]
  if ($tag -notmatch $TagPattern -or $InstalledRef -notmatch $TagPattern -or $tag -eq $InstalledRef) { return }
  if ([version]$tag.TrimStart('v') -le [version]$InstalledRef.TrimStart('v')) { return }
  Write-Host "terminal $tag is available; this command is $InstalledRef and may not know the newer commands. To install $tag, run:"
  Write-Host "  irm $Releases/download/$tag/install.ps1 | iex"
}
$Usage = "usage: terminal <status|update> [--wsl|--win] [--pinned]"
$Cmd = ""
$Target = "all"
$Pinned = $false
foreach ($arg in $args) {
  if ($arg -in "status", "update") { $Cmd = $arg }
  elseif ($arg -match '^--?(wsl|win)$') { $Target = $Matches[1] }
  elseif ($arg -match '^--?pinned$') { $Pinned = $true }
  else { Write-Host "terminal: unknown argument '$arg'"; Write-Host $Usage; Newer-Release-Hint; exit 2 }
}
if (-not $Cmd -or ($Pinned -and $Cmd -ne "update")) { Write-Host $Usage; exit 2 }

$H = $env:USERPROFILE
$Failed = $false

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

$script:FailedSteps = @()
$script:Updated = @()
$script:StepOk = $true

function Run-Step($name, [scriptblock]$block) {
  Write-Host "==> $name"
  $start = Get-Date
  $global:LASTEXITCODE = 0
  $ok = $true
  try { & $block } catch { Write-Host $_.Exception.Message -ForegroundColor Red; $ok = $false }
  if ($LASTEXITCODE -ne 0) { $ok = $false }
  $seconds = [int]((Get-Date) - $start).TotalSeconds
  if ($ok) { Write-Host "$($name): done ($seconds s)" }
  else { Write-Host "!! $($name): failed ($seconds s)" -ForegroundColor Red; $script:FailedSteps += $name }
  $script:StepOk = $ok
}

function Plan-Field($lines, $kind) {
  @($lines | Where-Object { $_ -like "$kind *" } | ForEach-Object { ($_ -split ' ', 3)[2] })
}

function Print-Summary($release, $checked, $agentsCount, $setupRan, $still) {
  if ($script:FailedSteps.Count) {
    $tail = if ($script:Updated.Count) { "; updated: $($script:Updated -join ', ')" } else { "" }
    Write-Host "Windows: failed: $($script:FailedSteps -join ', ')$tail" -ForegroundColor Red
  } elseif ($script:Updated.Count) {
    Write-Host "Windows: updated $($script:Updated -join ', ')" -ForegroundColor Green
  } elseif ($setupRan) {
    $tail = if ($still.Count) { " (still not up to date: $($still -join ' '))" } else { "" }
    Write-Host "Windows: setup $release ran; nothing changed$tail"
  } else {
    Write-Host "Windows: Everything is up to date (setup $release, $(if ($checked) { $checked } else { 0 }) tools, $agentsCount agents)" -ForegroundColor Green
  }
}

function Read-Plan($quiet) {
  $plan = [IO.Path]::GetTempFileName()
  $env:TERMINAL_STATUS_PLAN = $plan
  $env:TERMINAL_STATUS_SIDE = "windows"
  if ($quiet) {
    $env:TERMINAL_STATUS_QUIET = "1"
    & $script:Uvx --from "__SETUP_SOURCE__" terminal-setup --only status *> $null
  } else {
    $env:TERMINAL_STATUS_CHANGES_ONLY = "1"
    Run-Step "status check" { & $script:Uvx --from "__SETUP_SOURCE__" terminal-setup --only status }
    Remove-Item Env:TERMINAL_STATUS_CHANGES_ONLY -ErrorAction SilentlyContinue
  }
  Remove-Item Env:TERMINAL_STATUS_PLAN, Env:TERMINAL_STATUS_SIDE, Env:TERMINAL_STATUS_QUIET -ErrorAction SilentlyContinue
  $script:PlanLines = @(Get-Content $plan -ErrorAction SilentlyContinue)
  Remove-Item $plan -ErrorAction SilentlyContinue
}

function Update-Windows {
  Write-Host "Windows: checking the setup release, the tools and the agents..."
  $release = Target-Ref
  if (-not $release) {
    Write-Host "!! the latest terminal release could not be read from $Releases/latest, so terminal does not update. To update with the installed release, run: terminal update --pinned"
    $script:FailedSteps += "release lookup"
    Print-Summary $InstalledRef "" 0 $false @()
    return
  }
  Write-Host "setup: installed $InstalledRef, target $release"
  $script:Uvx = Find-Uvx
  $uvx = $script:Uvx
  if (-not $uvx) {
    Write-Host "!! uvx is not on the PATH, so terminal cannot check the tools. Run the terminal setup again to install uv."
    $script:FailedSteps += "status check"
    Print-Summary $release "" 0 $false @()
    return
  }
  Read-Plan $false
  $lines = $script:PlanLines
  if (-not $script:StepOk) { Print-Summary $release "" 0 $false @(); return }
  $outdated = Plan-Field $lines "outdated"
  $checked = (Plan-Field $lines "checked") | Select-Object -First 1
  $reasons = @()
  $setupRan = $false
  $still = @()
  if ($release -ne $InstalledRef) { $reasons += "setup $InstalledRef -> $release" }
  if ($outdated.Count) { $reasons += "not up to date: $($outdated -join ' ')" }
  if (-not $reasons.Count) {
    Write-Host "setup $($release): ok, every tool is up to date"
  } else {
    Write-Host "setup $release runs, because of $($reasons -join '; ')"
    $env:TERMINAL_SETUP_REF = $release
    if ($release -match $TagPattern) {
      Run-Step "setup $release" { Invoke-RestMethod "$Releases/download/$release/install.ps1" | Invoke-Expression }
    } else {
      Run-Step "setup $release" { & $uvx --python 3.14 --refresh-package terminal --from "__SETUP_SOURCE__" terminal-setup }
    }
    if ($script:StepOk) {
      $setupRan = $true
      Write-Host "checking what setup changed..."
      Read-Plan $true
      $after = Plan-Field $script:PlanLines "outdated"
      if ($release -ne $InstalledRef) { $script:Updated += "setup $InstalledRef -> $release" }
      foreach ($tool in $outdated) {
        if ($after -contains $tool) { $still += $tool } else { $script:Updated += $tool }
      }
    }
  }
  $agentsCount = 0
  $agents = Join-Path $H ".local\bin\agents.ps1"
  if (Test-Path $agents) {
    $report = [IO.Path]::GetTempFileName()
    $env:AGENTS_REPORT = $report
    $env:AGENTS_NESTED = "1"
    $env:AGENTS_CHANGES_ONLY = "1"
    $env:AGENTS_NO_HEADING = "1"
    Run-Step "agents update" { & $agents update "--win" }
    Remove-Item Env:AGENTS_REPORT, Env:AGENTS_NESTED, Env:AGENTS_CHANGES_ONLY, Env:AGENTS_NO_HEADING -ErrorAction SilentlyContinue
    $done = @(Get-Content $report -ErrorAction SilentlyContinue)
    Remove-Item $report -ErrorAction SilentlyContinue
    $agentsCount = @($done | Where-Object { $_ -match '^(ok|updated) (claude|codex|copilot)$' }).Count
    foreach ($line in $done) {
      if ($line -like "updated *") { $script:Updated += (($line -split ' ', 2)[1] -replace '^daemon$', 'codex daemon') }
    }
  }
  Print-Summary $release $checked $agentsCount $setupRan $still
}

function Update-Wsl {
  if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) { Write-Host "WSL: wsl.exe is not on the PATH, so terminal skips WSL."; return }
  $forward = @("update", "--wsl")
  if ($Pinned) { $forward += "--pinned" }
  Write-Host "==> WSL"
  & wsl.exe --exec bash -c 'p=~/.local/bin/terminal; test -x $p || { echo terminal is not in WSL, so terminal skips WSL. To add it, run the terminal setup.; exit 0; }; exec $p $@' terminal $forward
  if ($LASTEXITCODE -ne 0) { $script:FailedSteps += "WSL" }
}

if ($Cmd -eq "update") {
  if ($Target -ne "wsl") { Update-Windows }
  if ($Target -ne "win") { Update-Wsl }
  if ($script:FailedSteps.Count) { Write-Host "terminal update failed: $($script:FailedSteps -join ', ')" -ForegroundColor Red; exit 1 }
  $sides = if ($Target -eq "win") { "Windows" } elseif ($Target -eq "wsl") { "WSL" } else { "Windows and WSL" }
  Write-Host "terminal update: done ($sides)" -ForegroundColor Green
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
    $env:AGENTS_NO_HEADING = "1"
    & $agents status "--win"
    if ($LASTEXITCODE -ne 0) { $Failed = $true }
    Remove-Item Env:AGENTS_NESTED, Env:AGENTS_NO_HEADING -ErrorAction SilentlyContinue
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