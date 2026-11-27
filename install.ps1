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
        try {
            & { Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression }
        } catch {
            throw "The uv installer failed: $($_.Exception.Message)"
        }
        if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
            throw "The uv installer finished, but uv is not in $localBin."
        }
    } elseif ($uv.Source.StartsWith($env:USERPROFILE, [StringComparison]::OrdinalIgnoreCase)) {
        $installed = if ((& $uv.Source --version) -match '\d+\.\d+\.\d+') { $Matches[0] } else { '' }
        $latest = ''
        try {
            $request = [System.Net.WebRequest]::Create('https://github.com/astral-sh/uv/releases/latest')
            $request.Method = 'HEAD'
            $request.Timeout = 5000
            $response = $request.GetResponse()
            if ($response.ResponseUri.AbsoluteUri -match '/tag/v?(\d+\.\d+\.\d+)') { $latest = $Matches[1] }
            $response.Close()
        } catch {
            Write-Warning "github.com did not answer the uv release lookup within 5 s ($($_.Exception.Message)); setup continues with uv $installed."
        }
        if ($latest -and $latest -ne $installed) {
            try {
                & { Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression }
            } catch {
                Write-Warning "The uv installer failed ($($_.Exception.Message)); setup continues with uv $installed."
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
