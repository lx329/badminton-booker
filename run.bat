@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist .venv (
    echo 错误：未找到虚拟环境，请先运行 setup.bat
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
python main.py
pause
