& {
    $ErrorActionPreference = 'Stop'
    $ref = if ($env:TERMINAL_SETUP_REF) { $env:TERMINAL_SETUP_REF } else { 'main' }
    $sourceUrl = "https://github.com/niksavis/terminal/archive/$ref.zip"
    $setupArgs = @($args | Where-Object { $_ })
    if ($env:TERMINAL_SETUP_ARGS) {
        $setupArgs += @($env:TERMINAL_SETUP_ARGS -split '\s+' | Where-Object { $_ })
        Remove-Item Env:TERMINAL_SETUP_ARGS
    }

    $localBin = Join-Path $env:USERPROFILE '.local\bin'
    $env:Path = "$localBin;$env:Path"

    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $uv) {
        powershell -NoProfile -ExecutionPolicy Bypass -Command 'irm https://astral.sh/uv/install.ps1 | iex'
        if ($LASTEXITCODE -ne 0) {
            throw "The uv installer failed with exit code $LASTEXITCODE."
        }
    } elseif ($setupArgs -contains '--update' -and $uv.Source.StartsWith($env:USERPROFILE, [StringComparison]::OrdinalIgnoreCase)) {
        uv self update
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "uv self update failed with exit code $LASTEXITCODE; setup continues with the installed uv."
        }
    }

    uvx --python 3.14 --refresh-package terminal --from $sourceUrl terminal-setup @setupArgs
    if ($LASTEXITCODE -ne 0) {
        throw "terminal-setup failed with exit code $LASTEXITCODE."
    }
} @args
