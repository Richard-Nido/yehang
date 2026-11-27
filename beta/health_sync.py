"""只向手机开放最小 Puls 接口；本机管理 API 仍在 loopback。"""
import hmac
import json
import os
from pathlib import Path
import secrets
import socket
from threading import Lock, Thread
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

from adapters.puls_protocol import parse_batch, gunzip, BadRequest, UnsupportedVersion, TooLarge, MAX_DECODED
from storage import health_sync, workspace as ws

DEFAULT_USER = '5ea4d000-0000-4000-8000-000000000001'
MAX_BODY = 32 << 20


def create_receiver(token):
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware('http')
    async def authorize(request, call_next):
        if request.url.path == '/healthz' and request.method == 'GET':
            return JSONResponse({'ok': True})
        if not hmac.compare_digest(request.headers.get('authorization', ''), 'Bearer ' + token):
            return JSONResponse({'error': 'unauthorized'}, status_code=401)
        version = request.headers.get('x-puls-protocol', '1')
        if version != '1':
            return JSONResponse({'error': 'unsupported protocol version', 'supportedVersions': [1]}, status_code=400)
        return await call_next(request)

    @app.get('/v1/capabilities')
    def capabilities():
        return {'protocolVersions': [1], 'features': ['batches'], 'server': 'yehang', 'version': 'puls-preview-1'}

    @app.post('/v1/batches')
    async def ingest(request: Request):
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > MAX_BODY:
                return JSONResponse({'error': 'body too large'}, status_code=413)
        try:
            encoding = request.headers.get('content-encoding', 'identity').lower()
            if encoding == 'gzip':
                body = gunzip(bytes(raw))
            elif encoding in ('identity', ''):
                body = bytes(raw)
            else:
                raise BadRequest('unsupported content encoding')
            if len(body) > MAX_DECODED:
                raise TooLarge('body too large')
            batch = parse_batch(body.decode('utf-8'))
            user = str(UUID(request.headers.get('x-user-id') or DEFAULT_USER))
            # 同步写入在工作线程执行；不会占住本机浏览器的事件循环。
            from starlette.concurrency import run_in_threadpool
            def save():
                with ws.open_workspace() as db:
                    return health_sync.apply_batch(db, batch, user)
            return await run_in_threadpool(save)
        except UnsupportedVersion:
            return JSONResponse({'error': 'unsupported protocol version', 'supportedVersions': [1]}, status_code=400)
        except TooLarge:
            return JSONResponse({'error': 'body too large'}, status_code=413)
        except PermissionError as e:
            return JSONResponse({'error': str(e)}, status_code=403)
        except (BadRequest, ValueError, TypeError, KeyError, OverflowError):
            return JSONResponse({'error': '批次字段、时间、单位或记录身份无效，整批未导入'}, status_code=400)
        except Exception:
            return JSONResponse({'error': '暂时无法保存，请稍后重试'}, status_code=503)
    return app


class Controller:
    def __init__(self):
        self.server = None
        self.worker = None
        self.sock = None
        self.lock = Lock()
        self.token = None
        self.port = None

    def credential(self):
        path = Path(os.environ['YEHANG_DB_PATH']).parent / 'health-sync-token.json'
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('x', encoding='utf8') as f:
                json.dump({'token': secrets.token_urlsafe(32)}, f)
            if os.name != 'nt':
                path.chmod(0o600)
        return json.loads(path.read_text())['token']

    def start(self, port=8520):
        with self.lock:
            if self.worker and self.worker.is_alive():
                return self.info()
            sock = socket.socket()
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(('0.0.0.0', int(port)))
                sock.listen()
            except OSError:
                sock.close()
                raise ValueError('同步端口被占用，请换一个端口') from None
            self.token, self.port = self.credential(), sock.getsockname()[1]
            self.sock = sock
            self.server = uvicorn.Server(uvicorn.Config(create_receiver(self.token), access_log=False,
                log_config=None, ws='none', loop='asyncio', http='h11'))
            self.worker = Thread(target=self.server.run, kwargs={'sockets': [sock]}, daemon=True)
            self.worker.start()
            return self.info()

    def stop(self):
        with self.lock:
            if self.server:
                self.server.should_exit = True
            if self.worker:
                self.worker.join(timeout=10)
            if self.sock:
                self.sock.close()
            return self.info()

    def info(self):
        return {'running': bool(self.worker and self.worker.is_alive()), 'port': self.port,
                'token': self.token if self.worker and self.worker.is_alive() else None}


controller = Controller()
