& {
    $ErrorActionPreference = 'Stop'
    $ref = if ($env:TERMINAL_SETUP_REF) { $env:TERMINAL_SETUP_REF } else { 'main' }
    $sourceUrl = "https://github.com/niksavis/terminal/archive/$ref.zip"
    $setupArgs = @($args | Where-Object { $_ })
    if ($env:TERMINAL_SETUP_ARGS) {
        $setupArgs += @($env:TERMINAL_SETUP_ARGS -split '\s+' | Where-Object { $_ })
    }

    $localBin = Join-Path $env:USERPROFILE '.local\bin'
    $env:Path = "$localBin;$env:Path"

    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        powershell -NoProfile -ExecutionPolicy Bypass -Command 'irm https://astral.sh/uv/install.ps1 | iex'
        if ($LASTEXITCODE -ne 0) {
            throw "The uv installer failed with exit code $LASTEXITCODE."
        }
    }

    uvx --python 3.14 --refresh-package terminal --from $sourceUrl terminal-setup @setupArgs
    if ($LASTEXITCODE -ne 0) {
        throw "terminal-setup failed with exit code $LASTEXITCODE."
    }
} @args
