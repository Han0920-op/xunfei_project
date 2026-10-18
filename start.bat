@echo off
chcp 65001 >nul
title 智麦项目启动器

echo ============================
echo       智麦项目启动器
echo ============================

:: 启动后端 FastAPI
start "智麦后端" cmd /k "cd /d %~dp0back_end && call venv\Scripts\activate.bat && python -m uvicorn main:app --reload"

:: 启动前端静态服务器
start "智麦前端" cmd /k "cd /d %~dp0front_end && ..\back_end\venv\Scripts\python.exe -m http.server 8080"

echo.
echo 前后端启动命令已执行！
echo 后端默认地址:http://127.0.0.1:8000
echo 前端默认地址:http://127.0.0.1:8080
echo 请查看两个终端窗口。
start "" "http://127.0.0.1:8080"
pause