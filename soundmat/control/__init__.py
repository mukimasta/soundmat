"""控制接口：控制台与主机程序之间唯一的通道（ARCHITECTURE「控制接口」）。

状态通过一条 WebSocket 推送：连接时先发完整快照，之后只发生了变化的部分；
垫面这类高频数据单独以 ``mat`` 消息限频推送。命令和设置修改走 HTTP。
协议见 docs/implementation/CONTROL_API.md。
"""
from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..config import ROOT, Config
from ..exchange import Latest
from ..perception.model import MatSnapshot
from ..perception.virtual import VirtualMat
from ..perception.zones import geometry_json
from ..store import Store

CONSOLE_DIST = ROOT / "console" / "dist"
MAT_PUSH_HZ = 30.0


@dataclass
class ControlContext:
    """控制接口能接触到的东西。其他模块通过这里暴露的对象和命令接入。"""
    config: Config
    store: Store
    mat: Latest[MatSnapshot]
    virtual: VirtualMat | None = None
    # 额外的高频数据源，例如灯环预览：消息类型 → 保存可 JSON 化 dict 的最新值容器
    streams: dict[str, Latest[dict]] = field(default_factory=dict)


class ZoneBody(BaseModel):
    zone: int


def mat_message(snap: MatSnapshot) -> dict:
    vals = snap.pressure.values
    return {
        "type": "mat",
        "t": round(snap.t, 4),
        "source": snap.source,
        # 压力按千分之一取整，减小消息体积
        "pressure": [int(v * 1000 + 0.5) for v in vals.clip(0, 1)],
        "occupied": sorted(snap.state.occupied),
        "ringCounts": list(snap.state.ring_counts),
        "control": snap.state.control_pressure,
    }


def create_app(ctx: ControlContext, console_dist: Path | None = CONSOLE_DIST) -> FastAPI:
    app = FastAPI(title="SoundMat")

    def require_virtual() -> VirtualMat:
        if ctx.virtual is None:
            raise HTTPException(status_code=409, detail="当前没有使用虚拟垫子")
        return ctx.virtual

    @app.get("/api/state")
    def get_state() -> dict:
        return ctx.store.snapshot()

    @app.get("/api/geometry")
    def get_geometry() -> list[dict]:
        return geometry_json()

    @app.post("/api/virtual/toggle")
    def virtual_toggle(body: ZoneBody) -> dict:
        vm = require_virtual()
        try:
            present = vm.toggle(body.zone)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        return {"zone": body.zone, "stone": present}

    @app.post("/api/virtual/clear")
    def virtual_clear() -> dict:
        require_virtual().clear()
        return {"ok": True}

    @app.websocket("/ws")
    async def ws(socket: WebSocket) -> None:
        await socket.accept()
        loop = asyncio.get_running_loop()
        changes: asyncio.Queue = asyncio.Queue()

        def on_change(items):
            loop.call_soon_threadsafe(changes.put_nowait, items)

        unsubscribe = ctx.store.subscribe(on_change)
        try:
            await socket.send_json({
                "type": "hello",
                "geometry": geometry_json(),
                "config": ctx.config.describe(),
                "ledCount": ctx.config.light.led_count,
                "state": ctx.store.snapshot(),
            })
            sender = asyncio.create_task(_push(socket, ctx, changes))
            try:
                # 客户端不通过 WebSocket 发命令；这里只为及时发现断开
                while True:
                    await socket.receive_text()
            finally:
                sender.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await sender
        except WebSocketDisconnect:
            pass
        finally:
            unsubscribe()

    if console_dist and console_dist.is_dir():
        app.mount("/", StaticFiles(directory=console_dist, html=True), name="console")
    else:
        @app.get("/", response_class=HTMLResponse)
        def no_console() -> str:
            return ("<p>控制台还没有构建。在 <code>console/</code> 下运行 "
                    "<code>npm ci && npm run build</code>，或用 <code>npm run dev</code> 开发。</p>")

    return app


async def _push(socket: WebSocket, ctx: ControlContext, changes: asyncio.Queue) -> None:
    period = 1.0 / MAT_PUSH_HZ
    last_mat_version = -1
    last_mat_body = None
    stream_versions = {name: -1 for name in ctx.streams}
    while True:
        batch: list = []
        try:
            batch.extend(await asyncio.wait_for(changes.get(), timeout=period))
        except asyncio.TimeoutError:
            pass
        while not changes.empty():
            batch.extend(changes.get_nowait())
        if batch:
            await socket.send_json({"type": "patch", "changes": [[p, v] for p, v in batch]})
        snap, version = ctx.mat.get_versioned()
        if snap is not None and version != last_mat_version:
            last_mat_version = version
            msg = mat_message(snap)
            body = (msg["source"], msg["pressure"], msg["occupied"], msg["control"])
            if body != last_mat_body:  # 垫面没有变化时不重复推送
                last_mat_body = body
                await socket.send_json(msg)
        for name, latest in ctx.streams.items():
            data, v = latest.get_versioned()
            if data is not None and v != stream_versions[name]:
                stream_versions[name] = v
                await socket.send_json({"type": name, **data})
