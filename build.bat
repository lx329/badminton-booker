@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist .venv (
    echo 错误：未找到虚拟环境，请先运行 setup.bat
    pause
    exit /b 1
)

echo ========================================
echo  北师羽毛球预约系统 - 打包 EXE
echo ========================================
echo.

call .venv\Scripts\activate.bat

echo 正在打包...
pyinstaller --onefile --windowed --name badminton_booker ^
    --collect-all playwright ^
    --collect-all PySide6 ^
    --add-data "config.json;." ^
    --hidden-import playwright.async_api ^
    --hidden-import playwright.sync_api ^
    main.py

echo.
echo ========================================
echo  打包完成！EXE 位于 dist\badminton_booker.exe
echo ========================================
pause
