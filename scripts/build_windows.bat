@echo off
REM Build Captura.exe (run from the project root inside the Windows VM).
REM One-time setup:
REM   python -m venv .venv
REM   .venv\Scripts\pip install -r requirements.txt pyinstaller
.venv\Scripts\pyinstaller --noconfirm --windowed --name Captura ^
    --icon "%CD%\assets\icon.ico" ^
    --add-data "%CD%\assets;assets" ^
    --specpath build ^
    main.py
if errorlevel 1 exit /b 1
echo Built: dist\Captura\Captura.exe
echo Note: OCR needs Tesseract from github.com/UB-Mannheim/tesseract
echo (the app finds it in C:\Program Files\Tesseract-OCR automatically).
