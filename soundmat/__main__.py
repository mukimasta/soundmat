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

from . import config
from .app import ModeManager
from .core.led.writer import LEDWriter
from .core.sc_server import SCServerHandle
from .core.services import SharedServices


def build_args(argv=None):
    p = argparse.ArgumentParser(prog="soundmat", description="SoundMat 上位机")
    p.add_argument("manifest", nargs="?", default=str(config.DEFAULT_MANIFEST),
                   help="初始 manifest 路径（默认 jam/lofi_1.toml）")
    p.add_argument("--mock", metavar="REC", nargs="?", const="__manual__",
                   help="用 mock 传感数据源；给路径则回放 .npz，不给则手动注入模式")
    p.add_argument("--no-serial", action="store_true", help="不开串口（LED 虚拟模式）")
    p.add_argument("--no-web", action="store_true", help="不启动 Web 控制台")
    p.add_argument("--no-sc", action="store_true",
                   help="不启动 scsynth（仅跑逻辑/LED，离线调试）")
    return p.parse_args(argv)


def _open_shared_serial():
    import serial

    return serial.Serial(config.SERIAL_PORT, config.SERIAL_BAUD, timeout=1.0)


def main(argv=None) -> int:
    args = build_args(argv)

    # ── SC ──
    sc = SCServerHandle()
    if not args.no_sc:
        sc.boot()
        sc.load_synthdefs()

    # ── 传感器 + LED + 串口 ──
    shared_serial = None
    if args.mock:
        from .core.sensor.mock_reader import MockSensorReader

        recording = None if args.mock == "__manual__" else args.mock
        sensor = MockSensorReader(recording=recording)
    else:
        from .core.sensor.serial_reader import SerialSensorReader

        sensor = SerialSensorReader()
        if not args.no_serial:
            try:
                shared_serial = _open_shared_serial()
                sensor.attach_serial(shared_serial)
            except Exception as e:
                print(f"[main] 串口打开失败，转 mock: {e}")
                from .core.sensor.mock_reader import MockSensorReader

                sensor = MockSensorReader()

    leds = LEDWriter()
    if shared_serial is not None:
        leds.attach_serial(shared_serial)

    sensor.start()
    leds.start()

    services = SharedServices(sc=sc, sensor=sensor, leds=leds, osc=sc.osc)
    manager = ModeManager(services)

    if not args.no_sc:
        manager.switch_to(args.manifest)
    else:
        print("[main] --no-sc：跳过模式启动（无音频）")

    # ── Web ──
    web_thread = None
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

    # ── 信号等待 ──
    stop = threading.Event()

    def _shutdown(*_):
        print("\n[main] 收到退出信号，清理中…")
        stop.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    print("[main] 运行中。Ctrl-C 退出。")
    try:
        stop.wait()
    finally:
        manager.shutdown()
        sensor.stop()
        leds.stop()
        if shared_serial is not None:
            try:
                shared_serial.close()
            except Exception:
                pass
        sc.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
