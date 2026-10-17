"""命令行入口：``uv run soundmat [--virtual]``。"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import uvicorn

from .config import load_config
from .control import create_app
from .supervisor import Options, Supervisor


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="soundmat", description="SoundMat 主机程序")
    parser.add_argument("--virtual", action="store_true", help="使用虚拟垫子代替控制器（开发用）")
    parser.add_argument("--config", help="配置文件路径，默认 config/soundmat.toml")
    parser.add_argument("--data-dir", help="本机数据目录（设置、录音），默认是程序目录下的 data/")
    parser.add_argument("--host", help="控制接口监听地址，默认取配置")
    parser.add_argument("--port", type=int, help="控制接口端口，默认取配置")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config(args.config)
    opts = Options(virtual=args.virtual)
    if args.data_dir:
        opts.data_dir = Path(args.data_dir)
    sup = Supervisor(cfg, opts)
    sup.start()
    try:
        uvicorn.run(
            create_app(sup.control),
            host=args.host or cfg.control.host,
            port=args.port or cfg.control.port,
            ws="wsproto",
            log_level="warning",
        )
    finally:
        sup.stop()


if __name__ == "__main__":
    main()
