@echo off
setlocal

set NAME=OfflineBackupAssistant

echo Building %NAME%...

pyinstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --name %NAME% ^
  --add-binary "par2.exe;." ^
  --collect-all PySide6 ^
  --collect-all PIL ^
  main.py

echo Done. Output in dist\%NAME%
endlocal
