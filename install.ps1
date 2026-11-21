& {
    $ErrorActionPreference = 'Stop'
    $ref = if ($env:TERMINAL_SETUP_REF) { $env:TERMINAL_SETUP_REF } else { 'main' }
    $sourceUrl = "https://github.com/niksavis/terminal/archive/$ref.zip"
    $env:TERMINAL_SETUP_REF = $ref
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
    } elseif ($uv.Source.StartsWith($env:USERPROFILE, [StringComparison]::OrdinalIgnoreCase)) {
        $installed = if ((& $uv.Source --version) -match '\d+\.\d+\.\d+') { $Matches[0] } else { '' }
        $latest = ''
        try {
            $request = [System.Net.WebRequest]::Create('https://github.com/astral-sh/uv/releases/latest')
            $request.Method = 'HEAD'
            $response = $request.GetResponse()
            if ($response.ResponseUri.AbsoluteUri -match '/tag/v?(\d+\.\d+\.\d+)') { $latest = $Matches[1] }
            $response.Close()
        } catch {
            Write-Warning "The latest uv release could not be read; setup continues with uv $installed."
        }
        if ($latest -and $latest -ne $installed) {
            powershell -NoProfile -ExecutionPolicy Bypass -Command 'irm https://astral.sh/uv/install.ps1 | iex'
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "The uv installer failed with exit code $LASTEXITCODE; setup continues with uv $installed."
            }
        }
    }

    $env:TERMINAL_SETUP_BOOTSTRAP = '1'
    try {
        uvx --python 3.14 --refresh-package terminal --from $sourceUrl terminal-setup @setupArgs
    } finally {
        Remove-Item Env:TERMINAL_SETUP_BOOTSTRAP
    }
    if ($LASTEXITCODE -ne 0) {
        throw "terminal-setup failed with exit code $LASTEXITCODE."
    }
} @args
