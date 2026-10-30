@echo off
chcp 65001 >nul
title 智麦项目启动器

echo ============================
echo       智麦项目启动器
echo ============================

:: 启动后端 FastAPI（前端由后端同源托管，无需单独的静态服务器）
start "智麦后端" cmd /k "cd /d %~dp0back_end && call venv\Scripts\activate.bat && python -m uvicorn main:app --host 127.0.0.1 --port 8000"

echo.
echo 正在等待后端就绪，请稍候...

set "counter=0"
:wait_backend
curl -s -o nul http://127.0.0.1:8000/health
if not errorlevel 1 goto backend_ready
timeout /t 1 /nobreak >nul
set /a counter+=1
if %counter% geq 30 goto backend_timeout
goto wait_backend

:backend_ready
echo 后端已就绪，正在打开浏览器...
goto open_browser

:backend_timeout
echo [警告] 30 秒内后端未就绪，请查看「智麦后端」窗口中的报错信息。

:open_browser
start "" "http://127.0.0.1:8000/index.html"
pause