$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "No .venv found. Run: uv venv && uv pip install -r requirements.txt"
}

& ".venv\Scripts\python.exe" -m pip show pyinstaller *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing PyInstaller..."
    & ".venv\Scripts\python.exe" -m pip install pyinstaller
}

& ".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean translate_gui.spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed"
}

$exe = Join-Path $ProjectRoot "dist\EpubTsuyaku.exe"
if (Test-Path $exe) {
    $size = (Get-Item $exe).Length / 1MB
    Write-Host ""
    Write-Host "Built: $exe ($([math]::Round($size, 1)) MB)"
}
else {
    throw "Expected artifact not found: $exe"
}
