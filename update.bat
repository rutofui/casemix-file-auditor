@echo off
setlocal
cd /d "%~dp0"

echo ================================
echo Updating Casemix File Auditor
echo ================================

echo.
echo Checking Git...
git --version
IF ERRORLEVEL 1 (
    echo Git belum terinstall. Install Git for Windows terlebih dahulu.
    exit /b 1
)

echo.
echo Pulling latest code from GitHub...
git pull origin master
IF ERRORLEVEL 1 (
    echo git pull gagal. Pastikan folder ini hasil git clone dan koneksi internet aktif.
    exit /b 1
)

if not exist ".venv\Scripts\activate.bat" (
    echo Virtual environment belum ada. Jalankan install.bat terlebih dahulu.
    exit /b 1
)

echo.
echo Installing/updating Python dependencies...
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install --no-cache-dir -r requirements.txt
IF ERRORLEVEL 1 (
    echo pip install gagal.
    exit /b 1
)

echo.
echo ================================
echo Update completed.
echo ================================
exit /b 0
