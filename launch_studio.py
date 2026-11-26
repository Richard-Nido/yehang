"""Start the source application or the Windows desktop launcher."""

import argparse
import socket
import sys
from threading import Thread
import webbrowser

import uvicorn
from studio import app


def desktop(server, sock, url):
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title("夜航")
    root.resizable(False, False)
    from pathlib import Path

    root.iconbitmap(str(Path(sys._MEIPASS) / "packaging/yehang.ico"))
    panel = ttk.Frame(root, padding=22)
    panel.pack()
    ttk.Label(panel, text="夜航", font=("Microsoft YaHei UI", 17, "bold")).pack(
        anchor="w"
    )
    status = tk.StringVar(value="正在启动…")
    ttk.Label(panel, textvariable=status).pack(pady=(8, 16), anchor="w")
    open_button = ttk.Button(
        panel, text="打开夜航", command=lambda: webbrowser.open(url)
    )
    open_button.pack(fill="x")
    worker = Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    worker.start()

    def ready():
        if server.started:
            status.set("服务运行中 · " + url)
            webbrowser.open(url)
        elif worker.is_alive():
            root.after(100, ready)
        else:
            status.set("启动失败，请关闭后重新打开。")

    def exit_app():
        server.should_exit = True
        open_button.state(["disabled"])
        status.set("正在结束本机服务…")
        if worker.is_alive():
            root.after(150, exit_app)
        else:
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", exit_app)
    root.after(100, ready)
    root.mainloop()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8518)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", args.port))
        except OSError:
            sock.bind(("127.0.0.1", 0))
        url = f"http://127.0.0.1:{sock.getsockname()[1]}"
        sock.listen()
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                access_log=False,
                log_config=None,
                ws="none",
                loop="asyncio",
                http="h11",
            )
        )
        if getattr(sys, "frozen", False) and not args.no_browser:
            desktop(server, sock, url)
        else:
            if sys.stdout:
                print(url, flush=True)
            if not args.no_browser:
                webbrowser.open(url)
            server.run(sockets=[sock])


if __name__ == "__main__":
    main()
