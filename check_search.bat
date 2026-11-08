@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0back_end"
set "ZHIMAI_CHECK_PYTHON="
if exist "%~dp0.venv\Scripts\python.exe" set "ZHIMAI_CHECK_PYTHON=%~dp0.venv\Scripts\python.exe"
if not defined ZHIMAI_CHECK_PYTHON if exist "%~dp0back_end\venv\Scripts\python.exe" set "ZHIMAI_CHECK_PYTHON=%~dp0back_end\venv\Scripts\python.exe"
if not defined ZHIMAI_CHECK_PYTHON if exist "%~dp0back_end\.venv\Scripts\python.exe" set "ZHIMAI_CHECK_PYTHON=%~dp0back_end\.venv\Scripts\python.exe"
if not defined ZHIMAI_CHECK_PYTHON (
  echo 找不到项目虚拟环境，请先按 start.bat 的说明安装环境。
  goto finish
)
echo 智麦资料检索自检：检查本地知识库和真实网页，不调用模型、不输出密钥。
"%ZHIMAI_CHECK_PYTHON%" "%~dp0scripts\check_search.py"
:finish
pause
endlocal
