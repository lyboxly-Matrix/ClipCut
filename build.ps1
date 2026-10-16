$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
try {
    if (-not (Test-Path '.buildenv\Scripts\python.exe')) {
        py -3.11 -m venv .buildenv
        if ($LASTEXITCODE -ne 0) { throw 'Cannot create Python 3.11 build environment' }
    }
    & '.buildenv\Scripts\python.exe' -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
    & '.buildenv\Scripts\python.exe' -m PyInstaller --noconfirm ClipCut.spec
    if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
    Write-Host 'Success: dist\ClipCut\ClipCut.exe (keep the whole folder)'
} catch {
    Write-Error $_ -ErrorAction Continue
    Read-Host 'Build failed. Press Enter to close'
    exit 1
}
Read-Host 'Press Enter to close'
