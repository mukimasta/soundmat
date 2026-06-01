#!/usr/bin/env python
"""离线回放传感数据驱动某个模式（无 ESP32/传感器）。

用法：
  uv run python scripts/replay_test.py --manifest manifest/jam/lofi_1.toml \
      [--recording recordings/session.npz] [--seconds 30] [--no-sc]

不给 --recording 则用手动注入空垫面（仅验证管线不崩）。--no-sc 仅跑逻辑/LED 不发声。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from soundmat import config  # noqa: E402
from soundmat.app import ModeManager  # noqa: E402
from soundmat.core.led.writer import LEDWriter  # noqa: E402
from soundmat.core.sc_server import SCServerHandle  # noqa: E402
from soundmat.core.sensor.mock_reader import MockSensorReader  # noqa: E402
from soundmat.core.services import SharedServices  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", default=str(config.DEFAULT_MANIFEST))
    p.add_argument("--recording", default=None)
    p.add_argument("--seconds", type=float, default=30.0)
    p.add_argument("--no-sc", action="store_true")
    args = p.parse_args()

    sc = SCServerHandle()
    if not args.no_sc:
        sc.boot()
        sc.load_synthdefs()

    sensor = MockSensorReader(recording=args.recording)
    leds = LEDWriter()
    sensor.start()
    leds.start()

    services = SharedServices(sc=sc, sensor=sensor, leds=leds, osc=sc.osc)
    manager = ModeManager(services)
    if not args.no_sc:
        manager.switch_to(args.manifest)
        print(f"[replay] {args.manifest} 运行 {args.seconds}s …")
        if args.recording is None:
            # 无录制：手动放控制石 + 一颗旋律石，听一段
            time.sleep(0.5)
            sensor.inject([(0, 5), (7, 0), (4, 8), (2, 0)])
    else:
        print("[replay] --no-sc：仅逻辑/LED")

    try:
        time.sleep(args.seconds)
    except KeyboardInterrupt:
        pass
    finally:
        manager.shutdown()
        sensor.stop()
        leds.stop()
        sc.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
