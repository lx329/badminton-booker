@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo  北师羽毛球预约系统 - 环境初始化
echo ========================================
echo.

:: 1. 创建虚拟环境
if exist .venv (
    echo [跳过] 虚拟环境已存在
) else (
    echo [1/3] 创建虚拟环境...
    python -m venv .venv
    echo [完成] 虚拟环境创建成功
)

:: 2. 激活虚拟环境并安装依赖
echo.
echo [2/3] 安装 Python 依赖...
call .venv\Scripts\activate.bat
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
echo [完成] 依赖安装完成

:: 3. 安装 Playwright Chromium 浏览器
echo.
echo [3/3] 安装 Playwright Chromium 浏览器...
python -m playwright install chromium
echo [完成] Chromium 浏览器安装完成

echo.
echo ========================================
echo  初始化完成！双击 run.bat 启动应用
echo ========================================
pause
