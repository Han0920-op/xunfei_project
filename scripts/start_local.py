"""Local launcher: same-origin server, verified readiness, no automatic installs."""
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "back_end"
sys.path.insert(0, str(BACKEND))
from runtime import APP_VERSION, STREAM_PROTOCOL

URL = "http://127.0.0.1:8000"


def ready():
    # Local health checks should not travel through a system HTTP proxy.
    try:
        with build_opener(ProxyHandler({})).open(URL + "/api/agent/capabilities", timeout=1) as response:
            data = json.load(response)
            return (response.status == 200 and isinstance(data, dict) and data.get("server_version") == APP_VERSION
                    and data.get("stream_protocol") == STREAM_PROTOCOL)
    except (OSError, URLError, ValueError):
        return False


def port_in_use():
    try:
        with socket.create_connection(("127.0.0.1", 8000), timeout=0.5):
            return True
    except OSError:
        return False


def wait_until_ready(process, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        if ready() and process.poll() is None:
            return True
        time.sleep(0.3)
    return False


def main():
    print(f"智麦 {APP_VERSION} | Python {sys.version.split()[0]}", flush=True)
    if port_in_use():
        print("[提示] 8000 端口已有程序运行。请先关闭旧的智麦后端窗口，再重新启动。", flush=True)
        print("不会结束其他进程，也不会自动连接到旧版本。")
        return 1
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=BACKEND,
    )
    try:
        if not wait_until_ready(process):
            print("[启动失败] 后端未就绪，未打开浏览器。请查看上方报错。", flush=True)
            print('若提示缺少模块，请使用当前虚拟环境的 python -m pip install -r back_end/requirements.txt 更新依赖。')
            return 1
        print(f"[已就绪] {URL}/index.html\n请保留此窗口；关闭它会停止服务。按 Ctrl+C 停止。", flush=True)
        try:
            webbrowser.open(URL + "/index.html")
        except webbrowser.Error:
            print("无法自动打开浏览器，请手动打开上方地址。")
        return process.wait()
    except KeyboardInterrupt:
        print("\n正在停止智麦…", flush=True)
        return 0
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
