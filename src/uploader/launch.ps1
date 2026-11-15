$ErrorActionPreference = 'Stop'
$uploaderPython = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
$uploaderApp = Join-Path $PSScriptRoot 'app.py'
$uploaderUrl = 'http://127.0.0.1:49316/'
if (-not (Test-Path -LiteralPath $uploaderPython)) { throw 'Uploader environment is missing. See README.txt.' }
$uploaderReady = $false
try {
    $uploaderState = Invoke-RestMethod -Uri ($uploaderUrl + 'state') -TimeoutSec 2
    $uploaderReady = $uploaderState.release.uploader_version -eq '0.1.0'
} catch {}
if (-not $uploaderReady) {
    Start-Process -FilePath $uploaderPython -ArgumentList ('"' + $uploaderApp + '"') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
    for ($uploaderAttempt = 0; $uploaderAttempt -lt 20; $uploaderAttempt++) {
        Start-Sleep -Milliseconds 300
        try {
            $uploaderState = Invoke-RestMethod -Uri ($uploaderUrl + 'state') -TimeoutSec 2
            if ($uploaderState.release.uploader_version -eq '0.1.0') { $uploaderReady = $true; break }
        } catch {}
    }
}
if (-not $uploaderReady) { throw 'Uploader could not start on local port 49316. Run app.py to see the startup error.' }
Start-Process $uploaderUrl
