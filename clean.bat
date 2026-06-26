@echo off
title Clean Casemix File Auditor

echo ================================
echo Cleaning generated files
echo ================================

echo.
echo Removing Python cache...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -Path . -Directory -Recurse -Force -Filter __pycache__ | Where-Object { $_.FullName -notmatch '\\.venv\\' } | Remove-Item -Recurse -Force"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -Path . -File -Recurse -Force -Include *.pyc,*.pyo | Where-Object { $_.FullName -notmatch '\\.venv\\' } | Remove-Item -Force"

echo.
echo Removing local logs and pid files...
del /q .streamlit.log 2>nul
del /q .streamlit.pid 2>nul
del /q *.log 2>nul
del /q *.pid 2>nul

echo.
echo Removing exported review files...
del /q hasil_review_*.xlsx 2>nul

echo.
echo ================================
echo Cleanup completed.
echo ================================
pause
