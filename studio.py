"""夜航 Beta local API and web application."""

import json
import os
from pathlib import Path
import tempfile

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from beta import imports, provider, service
from storage import feedback, workspace as ws

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("YEHANG_DB_PATH", str(ROOT / ".local" / "interactive.sqlite3"))
MAX_UPLOAD = 1024**3
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]"]
)


@app.middleware("http")
async def local_browser(request, call_next):
    if request.method != "GET":
        origin = request.headers.get("origin")
        if (
            origin and origin != str(request.base_url).rstrip("/")
        ) or request.headers.get("x-yehang") != "1":
            return JSONResponse({"error": "请从本机夜航页面操作。"}, status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.exception_handler(ValueError)
def invalid(request, exc):
    return JSONResponse({"error": str(exc)}, status_code=400)


@app.exception_handler(Exception)
def failed(request, exc):
    return JSONResponse(
        {"error": "操作未完成，请检查输入或稍后重试。"}, status_code=500
    )


@app.get("/api/state")
def state(
    profile: str = service.PERSON,
    day: str | None = None,
    week: str | None = None,
    scheduleStart: str | None = None,
):
    with ws.open_workspace() as db:
        service.setup(db)
        return service.snapshot(db, profile, day, week, scheduleStart)


@app.get("/api/provider")
def get_provider(scope: str = "text"):
    return dict(provider.saved(scope), independent=provider.config_path(scope).exists())


@app.post("/api/provider/inherit")
def inherit_provider():
    provider.config_path("vision").unlink(missing_ok=True)
    return {}


@app.post("/api/provider")
def set_provider(body: dict):
    return provider.save(body)


@app.post("/api/models")
def get_models(body: dict):
    return {"models": provider.models(body)}


@app.post("/api/explanation")
def explain(body: dict):
    with ws.open_workspace() as db:
        state = service.snapshot(db, body["profile"], body.get("day"))
    labels = [
        "睡眠分钟",
        "静息心率 bpm",
        "HRV SDNN ms",
        "心率 bpm",
        "步数",
        "活动能量 kcal",
    ]
    summary = {label: state["series"][m] for label, m in zip(labels, service.SIGNALS)}
    if not any(v is not None for row in summary.values() for v in row):
        return {"source": "empty", "text": "导入健康记录后，这里会解释最近七天的变化。"}
    summary["观察日睡眠可能仅覆盖部分时段"] = state["partial"]
    prompt = (
        "请用简体中文，依据下列七天的日汇总解释观察日生理数据，最后一天为观察日。"
        "用两到三句，指出一个有数据支持的具体变化。null 表示缺测，不把缺失当作零。"
        "睡眠覆盖不完整时不要推断睡眠不足。不做诊断、因果推断、治疗或适岗建议。只返回纯文本。\n"
        + json.dumps(summary, ensure_ascii=False)
    )
    try:
        return {"source": "api", "text": provider.complete(prompt)[:3000]}
    except Exception:
        lines = []
        names = ["睡眠", "静息心率", "心率变异性", "心率", "步数", "活动能量"]
        units = ["分钟", "bpm", "ms", "bpm", "步", "kcal"]
        for idx, (label, values) in enumerate(list(summary.items())[:-1]):
            if values[-1] is None:
                continue
            prior = [v for v in values[:-1] if v is not None]
            text = f"{names[idx]}为 {values[-1]:g} {units[idx]}"
            if prior and not (label == "睡眠分钟" and state["partial"]):
                from statistics import median

                text += f"，此前 {len(prior)} 个有记录日的中位数为 {median(prior):g} {units[idx]}"
            if label == "睡眠分钟" and state["partial"]:
                text += "，记录仅覆盖部分时段"
            lines.append(text + "。")
        return {
            "source": "offline",
            "message": "模型调用失败",
            "text": "".join(lines[:3])
            or "观察日缺少有效数据，暂时无法与此前记录比较。",
        }


@app.post("/api/events")
def add_events(body: dict):
    with ws.open_workspace() as db:
        return service.save_events(db, body["profile"], body)


@app.post("/api/events/remove")
def remove_event(body: dict):
    with ws.open_workspace() as db:
        return service.remove(db, body["profile"], body)


@app.post("/api/plans")
def plan(body: dict):
    with ws.open_workspace() as db:
        return service.save_plan(db, body["profile"], body)


@app.post("/api/feedback")
def record_feedback(body: dict):
    p = body["profile"]
    with ws.open_workspace() as db:
        old = feedback.get(db, p, body["id"])
        basis_version = body.get("basisVersion", body["version"])
        keep = old.get("version") == basis_version and body["status"] != "跳过"
        feedback.save(
            db,
            p,
            service.mode(p),
            body["id"],
            body["version"],
            basis_version,
            body["feedbackRev"],
            body["status"],
            actual_start=old.get("actual_start") if keep else None,
            actual_end=old.get("actual_end") if keep else None,
            fatigue=None
            if body["status"] == "跳过"
            else body.get("fatigue", old.get("fatigue") if keep else None),
            note=old.get("note", "") if keep else "",
        )
    return {}


@app.post("/api/upload/{kind}")
async def upload(
    kind: str, request: Request, ext: str, week: str = "", profile: str = service.PERSON
):
    extension = "." + ext.lower()
    extensions = {
        "health": {".xml", ".json"},
        "schedule": {".png", ".jpg", ".jpeg", ".webp", ".pdf"},
    }
    if extension not in extensions.get(kind, set()):
        raise ValueError("不支持此文件格式。")
    if kind == "health" and profile != service.PERSON:
        raise ValueError("请切换到我的档案后导入健康记录。")
    if int(request.headers.get("content-length", 0)) > MAX_UPLOAD:
        return JSONResponse({"error": "单个文件上限为 1 GB。"}, status_code=413)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / ("upload" + extension)
        count = 0
        with path.open("wb") as dest:
            async for block in request.stream():
                count += len(block)
                if count > MAX_UPLOAD:
                    return JSONResponse(
                        {"error": "单个文件上限为 1 GB。"}, status_code=413
                    )
                dest.write(block)

        def process():
            if kind == "schedule":
                try:
                    return service.parse_roster(path, week)
                except ValueError:
                    raise
                except Exception:
                    raise ValueError(
                        "模型调用失败或文件无法读取，请检查多模态模型与文件，也可手动添加日程。"
                    ) from None
            try:
                with ws.open_workspace() as db:
                    return imports.import_health(path, db, profile)
            except (ValueError, OSError):
                raise
            except Exception:
                raise ValueError("文件格式不完整，本次导入已撤销。") from None

        return await run_in_threadpool(process)


@app.get("/")
def index():
    return FileResponse(ROOT / "web/index.html")


app.mount("/assets", StaticFiles(directory=ROOT / "web"), name="assets")
