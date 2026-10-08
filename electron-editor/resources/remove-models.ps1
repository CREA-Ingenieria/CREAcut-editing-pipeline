<# Called only after the user accepts model removal in the NSIS uninstaller. #>
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$cleanupFailed = $false

# Match setup_models.py. Delete only the two named files, never a cache folder.
try {
    $cacheRoot = if ($env:XDG_CACHE_HOME) { $env:XDG_CACHE_HOME } else {
        Join-Path $env:USERPROFILE '.cache'
    }
    $whisperCache = Join-Path $cacheRoot 'whisper'
    foreach ($modelFile in @('large-v3.pt', 'medium.pt')) {
        try {
            $modelPath = Join-Path $whisperCache $modelFile
            if (Test-Path -LiteralPath $modelPath) {
                if (!(Test-Path -LiteralPath $modelPath -PathType Leaf)) {
                    throw "Se esperaba un archivo: $modelPath"
                }
                Remove-Item -LiteralPath $modelPath -ErrorAction Stop
                Write-Output "Eliminado: $modelPath"
            } else {
                Write-Output "Ya ausente: $modelPath"
            }
        } catch {
            $cleanupFailed = $true
            Write-Output "ERROR Whisper ${modelFile}: $($_.Exception.Message)"
        }
    }
} catch {
    $cleanupFailed = $true
    Write-Output "ERROR al localizar Whisper: $($_.Exception.Message)"
}

$ollamaProcess = $null
try {
    # Never send a deletion to a remote Ollama server. The local server owns
    # its storage (including OLLAMA_MODELS), so do not delete blobs ourselves.
    $ollamaAddress = if ($env:OLLAMA_HOST) { $env:OLLAMA_HOST } else { 'http://127.0.0.1:11434' }
    if ($ollamaAddress -notmatch '://') { $ollamaAddress = "http://$ollamaAddress" }
    $ollamaUri = [Uri]$ollamaAddress
    if ($ollamaUri.Scheme -notin @('http', 'https') -or
        $ollamaUri.DnsSafeHost -notin @('localhost', '127.0.0.1', '::1')) {
        throw 'OLLAMA_HOST debe apuntar al servidor local para eliminar Gemma.'
    }

    $ollamaCommand = Get-Command ollama.exe -CommandType Application -ErrorAction SilentlyContinue
    $ollamaExecutable = if ($ollamaCommand) { $ollamaCommand.Source } else {
        Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
    }
    if (!(Test-Path -LiteralPath $ollamaExecutable -PathType Leaf)) {
        throw 'No se encontro Ollama. No se ha eliminado Gemma.'
    }

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $ollamaExecutable
    $startInfo.Arguments = 'rm gemma4:latest'
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.EnvironmentVariables['OLLAMA_HOST'] = $ollamaAddress
    $ollamaProcess = [System.Diagnostics.Process]::Start($startInfo)
    $stdout = $ollamaProcess.StandardOutput.ReadToEndAsync()
    $stderr = $ollamaProcess.StandardError.ReadToEndAsync()
    if (!$ollamaProcess.WaitForExit(30000)) {
        $ollamaProcess.Kill()
        throw 'Ollama no termino en 30 segundos. Comprueba Gemma con ollama list.'
    }
    Write-Output $stdout.GetAwaiter().GetResult()
    Write-Output $stderr.GetAwaiter().GetResult()
    if ($ollamaProcess.ExitCode -ne 0) {
        throw 'Ollama no confirmo la eliminacion. Abre Ollama y ejecuta: ollama rm gemma4:latest'
    }
    Write-Output 'Gemma 4 eliminado.'
} catch {
    $cleanupFailed = $true
    Write-Output "ERROR Gemma: $($_.Exception.Message)"
} finally {
    if ($ollamaProcess) { $ollamaProcess.Dispose() }
}

if ($cleanupFailed) { exit 1 }
exit 0
