param(
    [string]$Name = "OfflineBackupAssistant",
    [switch]$OneFile
)

$ErrorActionPreference = "Stop"

Write-Host "Building $Name..."

$oneFileFlag = ""
if ($OneFile) {
    $oneFileFlag = "--onefile"
}

pyinstaller `
    --noconfirm `
    --clean `
    --windowed `
    $oneFileFlag `
    --name $Name `
    --add-binary "par2.exe;." `
    --collect-all PySide6 `
    --collect-all PIL `
    main.py

Write-Host "Done. Output in dist\$Name"
