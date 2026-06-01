"""FastAPI app 构造 + 后台线程运行（设计文档 §6）。"""
from __future__ import annotations

import asyncio
from pathlib import Path

# 必须在模块全局：FastAPI 用 handler.__globals__ 解析 `ws: WebSocket` 注解；
# 若只在 build_app 内部 import，注解解析不到 → WebSocket 路由握手被拒(403)。
from fastapi import WebSocket, WebSocketDisconnect

from .. import config

STATIC_DIR = Path(__file__).resolve().parent / "static"


def build_app(manager):
    from fastapi import FastAPI
    from fastapi.responses import FileResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles

    from ..app import list_manifests
    from ..core.sensor.mock_reader import MockSensorReader

    app = FastAPI(title="SoundMat Control")

    # ── 页面 ──
    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/heatmap")
    def heatmap():
        return FileResponse(STATIC_DIR / "heatmap.html")

    @app.get("/debug")
    def debug():
        return FileResponse(STATIC_DIR / "debug.html")

    @app.get("/pad")
    def pad():
        return FileResponse(STATIC_DIR / "pad.html")

    # ── HTTP API ──
    @app.get("/api/status")
    def status():
        return manager.status()

    @app.get("/api/manifests")
    def manifests():
        return list_manifests()

    @app.post("/api/mode")
    async def set_mode(body: dict):
        manifest = body.get("manifest")
        if not manifest:
            return JSONResponse({"error": "missing manifest"}, status_code=400)
        try:
            return manager.switch_to(manifest)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.post("/api/transport")
    async def transport(body: dict):
        action = body.get("action")
        if action == "start":
            manager.start_current()
        elif action == "stop":
            manager.stop_current()
        else:
            return JSONResponse({"error": "action must be start|stop"}, status_code=400)
        return manager.status()

    @app.post("/api/params")
    async def params(body: dict):
        key = body.get("key")
        if key is None:
            return JSONResponse({"error": "missing key"}, status_code=400)
        manager.set_param(key, body.get("value"))
        return manager.status()

    # ── 虚拟垫面（mock 注入，仅 --mock 模式可用）──
    @app.post("/api/mock/cells")
    async def mock_cells(body: dict):
        sensor = manager.services.sensor
        if not isinstance(sensor, MockSensorReader):
            return JSONResponse(
                {"error": "not in mock mode — 用 --mock 启动"}, status_code=400
            )
        cells = [(int(c[0]), int(c[1])) for c in body.get("cells", [])]
        sensor.inject(cells)
        return {"ok": True, "count": len(cells)}

    @app.websocket("/api/mock/view")
    async def mock_view(ws: WebSocket):
        # 把 JamApp 每帧算好的 108 路 LED + 状态推给浏览器（== 装置真实灯环镜像）
        await ws.accept()
        try:
            while True:
                await ws.send_json({
                    "leds": manager.services.leds.latest(),
                    "status": manager.status(),
                })
                await asyncio.sleep(1 / 40)
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    # ── WebSocket 流 ──
    @app.websocket("/api/sensor_stream")
    async def sensor_stream(ws: WebSocket):
        await ws.accept()
        try:
            while True:
                frame = manager.services.sensor.latest()
                payload = {
                    "rings": config.NUM_RINGS,
                    "slices": config.NUM_SLICES,
                    "matrix": frame.matrix.tolist() if frame is not None else None,
                    "seq": frame.seq if frame is not None else -1,
                }
                await ws.send_json(payload)
                await asyncio.sleep(1 / 30)
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    @app.websocket("/api/event_stream")
    async def event_stream(ws: WebSocket):
        await ws.accept()
        try:
            while True:
                await ws.send_json(manager.status())
                await asyncio.sleep(1 / 10)
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    return app


def run_web(manager, host: str | None = None, port: int | None = None) -> None:
    """在后台线程里跑：自建事件循环 + uvicorn Server（不装信号处理器）。"""
    import uvicorn

    app = build_app(manager)
    cfg = uvicorn.Config(app, host=host or config.WEB_HOST, port=port or config.WEB_PORT,
                         log_level="warning", ws="wsproto")
    server = uvicorn.Server(cfg)
    server.install_signal_handlers = lambda: None  # 非主线程，禁用信号处理
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(server.serve())
