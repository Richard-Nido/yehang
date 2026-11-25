"""Start on loopback, opening the browser after binding a free port."""

import argparse
import socket
import webbrowser
import uvicorn

from studio import app

if __name__ == "__main__":
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
        print(url, flush=True)
        sock.listen()
        if not args.no_browser:
            webbrowser.open(url)
        uvicorn.Server(uvicorn.Config(app, access_log=False)).run(sockets=[sock])
