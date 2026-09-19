@echo off
cd /d "%~dp0"
rem Keep the virtualenv outside the project folder (OneDrive locks files inside .venv).
if not defined UV_PROJECT_ENVIRONMENT set UV_PROJECT_ENVIRONMENT=%USERPROFILE%\.venvs\ebook-manager
set PYTHONUTF8=1
uv run smartdoc
if errorlevel 1 (
    echo.
    echo App thoat voi loi. Nhan phim bat ky de dong cua so nay.
    pause >nul
)
