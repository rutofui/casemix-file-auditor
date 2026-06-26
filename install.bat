@echo off
title Install Casemix File Auditor

echo ================================
echo Installing Casemix File Auditor
echo ================================

echo.
echo Checking Python...
python --version
IF ERRORLEVEL 1 (
    echo Python belum terinstall.
    echo Silakan install Python 3.11 atau 3.12 terlebih dahulu.
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
echo ================================
pause
