"""Custom provider configuration. Credentials remain in the OS credential store."""

import base64
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import threading
from urllib.parse import quote, urlsplit

import httpx
import keyring
from PIL import Image, ImageOps
import pypdfium2 as pdfium

PROTOCOLS = {"chat", "responses", "anthropic", "gemini"}
pdf_lock = threading.Lock()  # PDFium is not thread-safe even for separate documents.


def config_path(scope="text"):
    if scope not in {"text", "vision"}:
        raise ValueError("未知模型用途。")
    return Path(os.environ["YEHANG_DB_PATH"]).parent / (
        "vision-provider.json" if scope == "vision" else "provider.json"
    )


def clean(raw):
    url = str(raw.get("base", "")).strip().rstrip("/")
    p = urlsplit(url)
    if (
        not p.hostname
        or p.query
        or p.fragment
        or p.username
        or p.password
        or not (
            p.scheme == "https"
            or p.scheme == "http"
            and p.hostname in {"localhost", "127.0.0.1", "::1"}
        )
    ):
        raise ValueError("请输入 HTTPS Base URL。本机服务也支持 HTTP。")
    protocol = raw.get("protocol")
    if protocol not in PROTOCOLS:
        raise ValueError("请选择接口协议。")
    return dict(base=url, protocol=protocol, model=str(raw.get("model", "")).strip())


def saved(scope="text"):
    path = config_path(scope)
    if path.exists():
        return json.loads(path.read_text(encoding="utf8"))
    if scope == "vision":
        return saved("text")
    return dict(
        base=os.getenv("YEHANG_API_BASE_URL", ""),
        model=os.getenv("YEHANG_API_MODEL", ""),
        protocol=os.getenv("YEHANG_API_PROTOCOL", "chat"),
    )


def identity(cfg):
    return sha256((cfg["protocol"] + "|" + cfg["base"]).encode()).hexdigest()


def secret(cfg, scope="text"):
    # The vision service inherits the text credential only while it inherits that service.
    if scope == "vision" and not config_path("vision").exists():
        scope = "text"
    key = keyring.get_password("yehang-beta", scope + "-" + identity(cfg))
    if key:
        return key
    if cfg["base"] == os.getenv("YEHANG_API_BASE_URL", "").rstrip("/") and cfg[
        "protocol"
    ] == os.getenv("YEHANG_API_PROTOCOL", "chat"):
        return os.getenv("YEHANG_API_KEY")
    return None


def save(raw):
    cfg = clean(raw)
    scope = raw.get("scope", "text")
    path = config_path(scope)
    if not cfg["model"]:
        raise ValueError("请填写或选择模型名称。")
    key = str(raw.get("key", "")).strip() or secret(cfg, scope)
    if not key:
        raise ValueError("请填写该供应商的 API Key。")
    keyring.set_password("yehang-beta", scope + "-" + identity(cfg), key)
    path.parent.mkdir(parents=True, exist_ok=True)
    from tempfile import NamedTemporaryFile

    with NamedTemporaryFile(
        mode="w", encoding="utf8", dir=path.parent, delete=False
    ) as f:
        json.dump(cfg, f)
    Path(f.name).replace(path)
    return cfg


def request(cfg, key, path, payload=None):
    if not key:
        raise ValueError("请先在模型设置中保存 API Key。")
    proto = cfg["protocol"]
    headers = (
        {"x-api-key": key, "anthropic-version": "2023-06-01"}
        if proto == "anthropic"
        else {"x-goog-api-key": key}
        if proto == "gemini"
        else {"Authorization": "Bearer " + key}
    )
    base = cfg["base"]
    if not urlsplit(base).path.strip("/"):
        base += "/v1beta" if proto == "gemini" else "/v1"
    try:
        with httpx.Client(
            timeout=httpx.Timeout(90, connect=12), follow_redirects=False
        ) as client:
            r = client.request(
                "POST" if payload is not None else "GET",
                base + path,
                headers=headers,
                json=payload,
            )
            if not r.is_success:
                raise ValueError(
                    f"供应商返回 HTTP {r.status_code}，请检查协议、密钥、模型和文件支持。"
                )
            return r.json()
    except httpx.HTTPError:
        raise ValueError("无法连接模型服务，请检查地址和网络。") from None


def models(raw):
    cfg = clean(raw)
    data = request(
        cfg, raw.get("key") or secret(cfg, raw.get("scope", "text")), "/models"
    )
    return [
        m.get("id") or m.get("name", "").removeprefix("models/")
        for m in data.get("data", data.get("models", []))
    ]


def complete(prompt, images=()):
    scope = "vision" if images else "text"
    cfg = clean(saved(scope))
    key, model, proto = secret(cfg, scope), cfg["model"], cfg["protocol"]
    if not model:
        raise ValueError("请在模型设置中选择模型。")
    if proto == "gemini":
        parts = [{"text": prompt}] + [
            {"inlineData": {"mimeType": "image/jpeg", "data": i}} for i in images
        ]
        result = request(
            cfg,
            key,
            "/models/"
            + quote(model.removeprefix("models/"), safe="")
            + ":generateContent",
            {"contents": [{"role": "user", "parts": parts}]},
        )
        texts = [
            p["text"]
            for p in result["candidates"][0]["content"]["parts"]
            if "text" in p and not p.get("thought")
        ]
    elif proto == "anthropic":
        parts = [{"type": "text", "text": prompt}] + [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": i},
            }
            for i in images
        ]
        result = request(
            cfg,
            key,
            "/messages",
            {
                "model": model,
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": parts}],
            },
        )
        texts = [p["text"] for p in result["content"] if p["type"] == "text"]
    elif proto == "responses":
        parts = [{"type": "input_text", "text": prompt}] + [
            {"type": "input_image", "image_url": "data:image/jpeg;base64," + i}
            for i in images
        ]
        result = request(
            cfg,
            key,
            "/responses",
            {"model": model, "input": [{"role": "user", "content": parts}]},
        )
        texts = [
            p["text"]
            for item in result["output"]
            for p in item.get("content", [])
            if p["type"] == "output_text"
        ]
    else:
        parts = [{"type": "text", "text": prompt}] + [
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + i}}
            for i in images
        ]
        result = request(
            cfg,
            key,
            "/chat/completions",
            {
                "model": model,
                "messages": [{"role": "user", "content": parts if images else prompt}],
            },
        )
        texts = [result["choices"][0]["message"]["content"]]
    text = "\n".join(texts).strip()
    if not text:
        raise ValueError("模型没有返回可读取的内容。")
    return text


def encoded(image):
    rgb = ImageOps.exif_transpose(image).convert("RGB")
    rgb.thumbnail((2100, 2100))
    buf = io.BytesIO()
    rgb.save(buf, "JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def image_batches(path):
    if path.suffix == ".pdf":
        with pdf_lock, pdfium.PdfDocument(path) as doc:
            pages = len(doc)
        for first in range(0, pages, 3):
            with pdf_lock, pdfium.PdfDocument(path) as doc:
                images = []
                for index in range(first, min(first + 3, pages)):
                    page = doc[index]
                    try:
                        bitmap = page.render(
                            scale=min(2.5, 2100 / max(page.get_size()))
                        )
                        try:
                            images.append(encoded(bitmap.to_pil()))
                        finally:
                            bitmap.close()
                    finally:
                        page.close()
            yield images
    else:
        with Image.open(path) as image:
            yield [encoded(image)]
