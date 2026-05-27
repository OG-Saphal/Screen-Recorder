@echo off
echo =============================================
echo  ScreenRec -- PyInstaller build
echo =============================================

REM Check that PyInstaller is available
python -m pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: PyInstaller not found.
    echo Run:  pip install pyinstaller
    pause
    exit /b 1
)

REM Build the single-file windowed executable
python -m pyinstaller ^
    --onefile ^
    --windowed ^
    --name ScreenRec ^
    --icon=icon.ico ^
    --add-data "ffmpeg.exe;." ^
    main.py

if errorlevel 1 (
    echo.
    echo BUILD FAILED. Check the output above for errors.
    pause
    exit /b 1
)

echo.
echo =============================================
echo  Build complete!
echo  Executable: dist\ScreenRec.exe
echo =============================================
pause
