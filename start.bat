@echo off
chcp 65001 >nul
setlocal
title 智麦项目启动器
cd /d "%~dp0"
echo ============================
echo       智麦项目启动器
echo ============================

set "ZHIMAI_PYTHON="
if exist "%~dp0.venv\Scripts\python.exe" set "ZHIMAI_PYTHON=%~dp0.venv\Scripts\python.exe"
if not defined ZHIMAI_PYTHON if exist "%~dp0back_end\venv\Scripts\python.exe" set "ZHIMAI_PYTHON=%~dp0back_end\venv\Scripts\python.exe"
if not defined ZHIMAI_PYTHON if exist "%~dp0back_end\.venv\Scripts\python.exe" set "ZHIMAI_PYTHON=%~dp0back_end\.venv\Scripts\python.exe"
if not defined ZHIMAI_PYTHON goto missing_environment

echo 使用 Python: "%ZHIMAI_PYTHON%"
"%ZHIMAI_PYTHON%" -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 goto invalid_python
"%ZHIMAI_PYTHON%" "%~dp0scripts\start_local.py"
if errorlevel 1 echo [未成功启动] 请保留本窗口的报错文字。
goto finish

:missing_environment
echo [找不到虚拟环境] 已检查根目录 .venv、back_end\venv、back_end\.venv。
echo 请在仓库根目录打开终端，执行：
echo   py -3 -m venv .venv
echo   .venv\Scripts\python.exe -m pip install -r back_end\requirements.txt
echo 然后再次双击 start.bat。不会修改或覆盖你的 .env。
goto finish

:invalid_python
echo [Python 不可用] 请安装 Python 3.10 或更新版本，并检查上方虚拟环境是否已被移动。

:finish
pause
endlocal
