"""python -m soundmat 入口 / `soundmat` CLI。

启动流程（设计文档 §7）：
  1. 解析命令行（默认 manifest/jam/lofi_1.toml）
  2. 启动 scsynth 子进程
  3. 加载全部 .scsyndef（两个模式的 SynthDef）
  4. 启动 SensorReader（串口 / mock）后台线程
  5. 启动 LEDWriter 后台线程
  6. 构造 SharedServices → ModeManager
  7. manager.switch_to(initial_manifest)
  8. 启动 Web 控制台后台线程
  9. 主线程进入信号等待
"""
from __future__ import annotations

import argparse
import signal
import sys
import threading
import time

from . import config
from .app import ModeManager
from .core.esp32_serial import (
    open_esp32_serial,
    pick_serial_port,
    print_serial_ports,
    wait_for_esp32_boot,
)
from .core.led.writer import LEDWriter
from .core.sc_server import SCServerHandle
from .core.services import SharedServices

START_MAX_ATTEMPTS = 5


def build_args(argv=None):
    p = argparse.ArgumentParser(prog="soundmat", description="SoundMat 上位机")
    p.add_argument("manifest", nargs="?", default=str(config.DEFAULT_MANIFEST),
                   help="初始 manifest 路径（默认 jam/lofi_1.toml）")
    p.add_argument("--mock", metavar="REC", nargs="?", const="__manual__",
                   help="用 mock 传感数据源；给路径则回放 .npz，不给则手动注入模式")
    p.add_argument("--port", default=None,
                   help="ESP32 串口路径，或 auto（默认，Mac/Pi 自动识别）")
    p.add_argument("--list-ports", action="store_true", help="列出可用串口后退出")
    p.add_argument("--no-serial", action="store_true", help="不开串口（LED 虚拟模式）")
    p.add_argument("--no-web", action="store_true", help="不启动 Web 控制台")
    p.add_argument("--no-sc", action="store_true",
                   help="不启动 scsynth（仅跑逻辑/LED，离线调试）")
    return p.parse_args(argv)


def _connect_esp32(port_arg: str) -> tuple[object, str, bool]:
    """打开串口并等待固件 S 帧。返回 (serial, resolved_port, boot_ok)。"""
    port = pick_serial_port(port_arg)
    ser = open_esp32_serial(port, config.SERIAL_BAUD)
    print(f"[main] 串口 {port} @ {config.SERIAL_BAUD}")
    print("[main] 等待 ESP32 就绪（首帧 S:）…", end="", flush=True)
    ready = wait_for_esp32_boot(ser, timeout=8.0)
    if ready:
        print(" ok")
        ser.reset_input_buffer()
    else:
        print(" 超时（8s 内无 S 帧，仍继续）")
    return ser, port, ready


def _run(args) -> int:
    port_arg = args.port if args.port is not None else config.SERIAL_PORT

    sc = SCServerHandle()
    sensor = None
    leds = None
    manager = None
    shared_serial = None

    try:
        if not args.no_sc:
            sc.boot()
            sc.load_synthdefs()

        serial_port: str | None = None
        serial_ready = False
        serial_lost = threading.Event()
        serial_watch = False

        def _on_serial_lost() -> None:
            serial_lost.set()

        if args.mock:
            from .core.sensor.mock_reader import MockSensorReader

            config.WIRE_SLICE_MIRROR = False  # 虚拟垫已是 CW slice 编号
            recording = None if args.mock == "__manual__" else args.mock
            sensor = MockSensorReader(recording=recording)
        else:
            from .core.sensor.serial_reader import SerialSensorReader

            if not args.no_serial:
                try:
                    shared_serial, serial_port, serial_ready = _connect_esp32(port_arg)
                    serial_watch = True
                    sensor = SerialSensorReader(port=port_arg, on_serial_lost=_on_serial_lost)
                    sensor.attach_serial(shared_serial)
                except Exception as e:
                    print(f"[main] 串口打开失败，转 mock: {e}")
                    from .core.sensor.mock_reader import MockSensorReader

                    config.WIRE_SLICE_MIRROR = False
                    sensor = MockSensorReader()
            else:
                sensor = SerialSensorReader(port=port_arg)

        leds = LEDWriter(on_serial_lost=_on_serial_lost if serial_watch else None)
        if shared_serial is not None:
            leds.attach_serial(shared_serial)

        sensor.start()
        leds.start()

        services = SharedServices(
            sc=sc,
            sensor=sensor,
            leds=leds,
            osc=sc.osc,
            serial_port=serial_port,
            serial_ready=serial_ready,
        )
        manager = ModeManager(services)

        if not args.no_sc:
            manager.switch_to(args.manifest)
        else:
            print("[main] --no-sc：跳过模式启动（无音频）")

        if not args.no_web:
            try:
                from .web.server import run_web

                web_thread = threading.Thread(
                    target=run_web, args=(manager,), daemon=True, name="web"
                )
                web_thread.start()
                print(f"[main] Web 控制台 http://{config.WEB_HOST}:{config.WEB_PORT}")
            except Exception as e:
                print(f"[main] Web 控制台启动失败: {e}")

        stop = threading.Event()

        def _shutdown(*_):
            print("\n[main] 收到退出信号，清理中…")
            stop.set()

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)
        print("[main] 运行中。Ctrl-C 退出。")
        lost_at: float | None = None
        while not stop.is_set():
            if serial_watch and serial_lost.is_set():
                if lost_at is None:
                    lost_at = time.monotonic()
                    print(f"[main] 串口断开，{config.SERIAL_LOST_EXIT_SEC:g}s 后退出…")
                elif time.monotonic() - lost_at >= config.SERIAL_LOST_EXIT_SEC:
                    stop.set()
                    break
            stop.wait(timeout=0.2)
        return 0
    finally:
        if manager is not None:
            manager.shutdown()
        if sensor is not None:
            sensor.stop()
        if leds is not None:
            leds.stop()
        if shared_serial is not None:
            try:
                shared_serial.close()
            except Exception:
                pass
        sc.quit()


def main(argv=None) -> int:
    args = build_args(argv)

    if args.list_ports:
        print_serial_ports()
        return 0

    for attempt in range(1, START_MAX_ATTEMPTS + 1):
        try:
            return _run(args)
        except KeyboardInterrupt:
            print("\n[main] 已中断")
            return 130
        except Exception as e:
            if attempt >= START_MAX_ATTEMPTS:
                print(f"[main] 启动失败，已尝试 {START_MAX_ATTEMPTS} 次: {e}", file=sys.stderr)
                return 1
            wait = min(attempt, 3)
            print(f"[main] 启动失败 ({attempt}/{START_MAX_ATTEMPTS}): {e}")
            print(f"[main] {wait}s 后重试…")
            time.sleep(wait)


if __name__ == "__main__":
    sys.exit(main())
