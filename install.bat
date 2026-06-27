@echo off
title Install Casemix File Auditor

echo ================================
echo Installing Casemix File Auditor
echo ================================

echo.
echo Checking Git...
git --version
IF ERRORLEVEL 1 (
    echo Git belum terinstall.
    echo Unduh Git for Windows dari https://git-scm.com/download/win
    pause
    exit /b 1
)

echo.
echo Checking Python...
python --version
IF ERRORLEVEL 1 (
    echo Python belum terinstall.
    echo Silakan install Python 3.11 atau 3.12 terlebih dahulu.
    echo Pastikan opsi "Add Python to PATH" dicentang saat instalasi.
    pause
    exit /b
)

echo.
echo Creating virtual environment...
python -m venv .venv

echo.
echo Activating virtual environment...
call .venv\Scripts\activate

echo.
echo Upgrading pip...
python -m pip install --upgrade pip

echo.
echo Installing requirements...
pip install --no-cache-dir -r requirements.txt

echo.
echo ================================
echo Installation completed.
echo Jalankan run_app.bat untuk membuka aplikasi.
echo ================================
pause
