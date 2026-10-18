"""控制接口：控制台与主机程序之间唯一的通道（ARCHITECTURE「控制接口」）。

状态通过一条 WebSocket 推送：连接时先发完整快照，之后只发生了变化的部分；
垫面这类高频数据单独以 ``mat`` 消息限频推送（最多 30 次/秒），灯环预览等数据流有新值就推送。
推送由数据变化唤醒，不按固定间隔轮询，所以不会因为两边节奏错开而丢帧。命令和设置修改走 HTTP。
协议见 docs/implementation/CONTROL_API.md。
"""
from __future__ import annotations

import asyncio
import contextlib
import ipaddress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..config import ROOT, Config
from ..errors import Conflict, UserError
from ..exchange import Latest
from ..perception.model import MatSnapshot
from ..perception.virtual import VirtualMat
from ..perception.zones import geometry_json
from ..rates import RateMeter
from ..store import Store
from ..store.settings import Settings
from ..timebase import system_time
from .download import zip_stream

CONSOLE_DIST = ROOT / "console" / "dist"
MAT_PUSH_HZ = 30.0
PATCH_HZ = 30.0      # 状态变化合批推送的上限


class Recordings(Protocol):
    """控制接口用到的录制功能（``soundmat.recorder.Recorder``）。"""
    def request_start(self) -> None: ...
    def request_stop(self) -> None: ...
    def list(self) -> list[dict]: ...
    def folder_of(self, name: str) -> Path: ...


class Updates(Protocol):
    """控制接口用到的软件更新功能（``soundmat.updater.Updater``）。"""
    enabled: bool
    def available(self) -> list[dict]: ...
    def start_update(self, tag: str) -> None: ...
    def rollback(self) -> None: ...


@dataclass
class ControlContext:
    """控制接口能接触到的东西。其他模块通过这里暴露的对象和命令接入。

    命令拒绝请求时抛出 ``soundmat.errors.UserError``，由控制接口统一转成 HTTP 状态码。
    """
    config: Config
    store: Store
    mat: Latest[MatSnapshot]
    settings: Settings
    play: Callable[[str], None]                      # 切换到一份编排
    test_tone: Callable[[int], None]                 # 逐声道测试音
    recorder: Recordings
    updater: Updates
    virtual: VirtualMat | None = None                # 只在使用虚拟垫子时存在
    # 额外的高频数据源，例如灯环预览：消息类型 → 保存可 JSON 化 dict 的最新值容器
    streams: dict[str, Latest[dict]] = field(default_factory=dict)
    # 每个 WebSocket 连接实际推送的帧率：连接序号 → 消息类型 → 速率计
    push_rates: dict[int, dict[str, RateMeter]] = field(default_factory=dict)

    def push_rate(self, kind: str) -> float | None:
        """所有连接里这类消息的最高实际推送帧率；没有控制台连着时为 None。"""
        rates = [r[kind].rate() for r in list(self.push_rates.values()) if kind in r]
        return max(rates) if rates else None

    def rates(self) -> dict[str, dict]:
        """给系统监测：推到控制台的垫面和灯环预览的实际帧率。两者都只在有变化时推送，期望值是上限。"""
        return {
            "pushMat": {"actual": self.push_rate("mat"), "expected": MAT_PUSH_HZ},
            "pushLeds": {"actual": self.push_rate("leds"), "expected": self.config.light.refresh_hz},
        }


TAILSCALE = ipaddress.ip_network("100.64.0.0/10")


def may_update(client_host: str | None) -> bool:
    """只有从本机或 Tailscale 来的请求能发起更新和回退（控制台不设登录，热点上的人只能看）。"""
    if not client_host:
        return False
    if client_host in ("localhost", "testclient"):
        return True
    try:
        ip = ipaddress.ip_address(client_host)
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_loopback or (ip.version == 4 and ip in TAILSCALE)


class UpdateBody(BaseModel):
    tag: str


class ZoneBody(BaseModel):
    zone: int


class SettingsBody(BaseModel):
    changes: dict


class ToneBody(BaseModel):
    channel: int


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

    @app.exception_handler(UserError)
    def user_error(request: Request, e: UserError) -> JSONResponse:
        return JSONResponse(status_code=e.status, content={"detail": str(e)})

    def virtual() -> VirtualMat:
        if ctx.virtual is None:
            raise Conflict("当前没有使用虚拟垫子")
        return ctx.virtual

    def updater(request: Request) -> Updates:
        if not may_update(request.client.host if request.client else None):
            raise HTTPException(status_code=403, detail="只有从本机或 Tailscale 打开的控制台能更新")
        return ctx.updater

    @app.get("/api/state")
    def get_state() -> dict:
        return ctx.store.snapshot()

    @app.get("/api/geometry")
    def get_geometry() -> list[dict]:
        return geometry_json()

    @app.post("/api/virtual/toggle")
    def virtual_toggle(body: ZoneBody) -> dict:
        return {"zone": body.zone, "stone": virtual().toggle(body.zone)}

    @app.post("/api/virtual/clear")
    def virtual_clear() -> dict:
        virtual().clear()
        return {"ok": True}

    @app.post("/api/arrangements/{arrangement_id}/play")
    def play(arrangement_id: str) -> dict:
        ctx.play(arrangement_id)
        return {"ok": True}

    @app.post("/api/settings")
    def update_settings(body: SettingsBody) -> dict:
        return {"applied": ctx.settings.update(body.changes)}

    @app.post("/api/audio/test-tone")
    def test_tone(body: ToneBody) -> dict:
        ctx.test_tone(body.channel)
        return {"ok": True}

    @app.post("/api/recording/start")
    def recording_start() -> dict:
        ctx.recorder.request_start()
        return {"ok": True}

    @app.post("/api/recording/stop")
    def recording_stop() -> dict:
        ctx.recorder.request_stop()
        return {"ok": True}

    @app.get("/api/recordings")
    def recordings() -> list[dict]:
        return ctx.recorder.list()

    @app.get("/api/recordings/{name}/download")
    def recording_download(name: str):
        folder = ctx.recorder.folder_of(name)
        return StreamingResponse(zip_stream(folder), media_type="application/zip",
                                 headers={"Content-Disposition": f"attachment; filename*=UTF-8''{folder.name}.zip"})

    @app.get("/api/update")
    def update_info(request: Request) -> dict:
        """软件更新面板的数据：能否更新、当前状态，以及 GitHub 上可以安装的版本（能更新时才列出）。"""
        up = ctx.updater
        allowed = up.enabled and may_update(request.client.host if request.client else None)
        out: dict = {"allowed": allowed, "enabled": up.enabled, "available": [], "error": None}
        if allowed:
            try:
                out["available"] = up.available()
            except Exception as e:      # GitHub 连不上：面板照常打开，写明原因
                out["error"] = f"读取 GitHub 上的版本失败：{e}"
        return out

    @app.post("/api/update", status_code=202)
    def update_start(body: UpdateBody, request: Request) -> dict:
        updater(request).start_update(body.tag)
        return {"ok": True}

    @app.post("/api/update/rollback", status_code=202)
    def update_rollback(request: Request) -> dict:
        updater(request).rollback()
        return {"ok": True}

    @app.websocket("/ws")
    async def ws(socket: WebSocket) -> None:
        await socket.accept()
        loop = asyncio.get_running_loop()
        changes: asyncio.Queue = asyncio.Queue()
        wake = asyncio.Event()

        def nudge() -> None:
            loop.call_soon_threadsafe(wake.set)

        def on_change(items):
            loop.call_soon_threadsafe(changes.put_nowait, items)
            nudge()

        unsubs = [ctx.store.subscribe(on_change), ctx.mat.subscribe(nudge),
                  *(latest.subscribe(nudge) for latest in ctx.streams.values())]
        conn = id(socket)
        ctx.push_rates[conn] = {"mat": RateMeter(), **{name: RateMeter() for name in ctx.streams}}
        try:
            await socket.send_json({
                "type": "hello",
                "geometry": geometry_json(),
                "config": ctx.config.describe(),
                "ledCount": ctx.config.light.led_count,
                "state": ctx.store.snapshot(),
            })
            sender = asyncio.create_task(_push(socket, ctx, changes, wake, ctx.push_rates[conn]))
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
            for unsub in unsubs:
                unsub()
            ctx.push_rates.pop(conn, None)

    if console_dist and console_dist.is_dir():
        app.mount("/", StaticFiles(directory=console_dist, html=True), name="console")
    else:
        @app.get("/", response_class=HTMLResponse)
        def no_console() -> str:
            return ("<p>控制台还没有构建。在 <code>console/</code> 下运行 "
                    "<code>npm ci && npm run build</code>，或用 <code>npm run dev</code> 开发。</p>")

    return app


async def _push(socket: WebSocket, ctx: ControlContext, changes: asyncio.Queue, wake: asyncio.Event,
                rates: dict[str, RateMeter]) -> None:
    mat_period = 1.0 / MAT_PUSH_HZ
    patch_period = 1.0 / PATCH_HZ
    pending: list = []
    last_patch_sent = -1.0
    last_mat_version = -1
    last_mat_body = None
    last_mat_sent = -1.0
    stream_versions = {name: -1 for name in ctx.streams}
    timeout = 0.5
    while True:
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(wake.wait(), timeout=timeout)
        wake.clear()
        timeout = 0.5
        while not changes.empty():
            pending.extend(changes.get_nowait())
        if pending:
            now = system_time()
            wait = last_patch_sent + patch_period - now
            if wait > 0:
                timeout = min(timeout, wait)  # 状态变化合批：到时间再一起发
            else:
                await socket.send_json({"type": "patch", "changes": [[p, v] for p, v in pending]})
                pending = []
                last_patch_sent = now
        snap, version = ctx.mat.get_versioned()
        if snap is not None and version != last_mat_version:
            now = system_time()
            wait = last_mat_sent + mat_period - now
            if wait > 0:
                timeout = min(timeout, wait)  # 垫面限频：到时间再发这一份最新的
            else:
                last_mat_version = version
                msg = mat_message(snap)
                body = (msg["source"], msg["pressure"], msg["occupied"], msg["control"])
                if body != last_mat_body:  # 垫面没有变化时不重复推送
                    last_mat_body = body
                    last_mat_sent = now
                    await socket.send_json(msg)
                    rates["mat"].tick(now)
        for name, latest in ctx.streams.items():
            data, v = latest.get_versioned()
            if data is not None and v != stream_versions[name]:
                stream_versions[name] = v
                await socket.send_json({"type": name, **data})
                rates[name].tick()
