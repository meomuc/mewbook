@echo off
cd /d "%~dp0"
set UV_PROJECT_ENVIRONMENT=C:\Users\slook\.venvs\ebook-manager
set PYTHONUTF8=1
uv run smartdoc
if errorlevel 1 (
    echo.
    echo App thoat voi loi. Nhan phim bat ky de dong cua so nay.
    pause >nul
)
