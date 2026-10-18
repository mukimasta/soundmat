"""命令行入口：``uv run soundmat [--virtual]``。

没有在运行的合成器服务时自己启动一个（退出时一起关掉，见 sound/scsynth_process.py），
启动后打印控制台能直接点开的网址。
"""
from __future__ import annotations

import argparse
import logging
import socket
from pathlib import Path

import uvicorn

from .config import load_config
from .control import create_app
from .monitor.probes import local_name
from .sound.scsynth_process import ensure_scsynth
from .supervisor import Options, Supervisor


def lan_address() -> str | None:
    """本机在局域网里的地址（出口网卡的 IPv4）；没有联网时为 None。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))     # 不发送任何数据，只为得到出口地址
        addr = s.getsockname()[0]
        s.close()
    except OSError:
        return None
    return None if addr.startswith("127.") else addr


def console_urls(bind_host: str, port: int, hostname: str | None, address: str | None) -> list[tuple[str, str]]:
    """控制台的网址：本机一个；监听所有网卡时再加局域网名字和地址。"""
    urls = [("本机", f"http://localhost:{port}")]
    if bind_host in ("0.0.0.0", "::", ""):
        name = local_name(hostname)
        if name:
            urls.append(("局域网", f"http://{name}:{port}"))
        if address:
            urls.append(("局域网", f"http://{address}:{port}"))
    return urls


def print_urls(urls: list[tuple[str, str]]) -> None:
    print("\nSoundMat 控制台", flush=True)
    width = max(2 * len(label) for label, _ in urls)      # 汉字在终端里占两格
    last = None
    for label, url in urls:
        shown = label if label != last else ""
        print(f"  {shown}{' ' * (width - 2 * len(shown))}  {url}", flush=True)
        last = label
    print(flush=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="soundmat", description="SoundMat 主机程序")
    parser.add_argument("--virtual", action="store_true", help="使用虚拟垫子代替控制器（开发用）")
    parser.add_argument("--config", help="配置文件路径，默认 config/soundmat.toml")
    parser.add_argument("--data-dir", help="本机数据目录（设置、录音），默认是程序目录下的 data/")
    parser.add_argument("--no-synth", action="store_true",
                        help="不连接合成器服务，使用只记录指令、不发声的声音引擎")
    parser.add_argument("--port-serial", dest="serial", default="auto",
                        help="控制器串口，默认 auto（自动选择 USB 串口）")
    parser.add_argument("--host", help="控制接口监听地址，默认取配置")
    parser.add_argument("--port", type=int, help="控制接口端口，默认取配置")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config(args.config)
    opts = Options(virtual=args.virtual, serial_port=args.serial,
                   synth="recording" if args.no_synth else "scsynth")
    if args.data_dir:
        opts.data_dir = Path(args.data_dir)
    sup = Supervisor(cfg, opts)
    synth_proc = None
    if not args.no_synth:
        synth_proc = ensure_scsynth(cfg.synth.host, cfg.synth.port, sup.engine.layout.channels,
                                    cfg.sound.expected_sample_rate)
    host = args.host or cfg.control.host
    port = args.port or cfg.control.port
    sup.start()
    try:
        print_urls(console_urls(host, port, socket.gethostname(), lan_address()))
        uvicorn.run(create_app(sup.control), host=host, port=port, ws="wsproto", log_level="warning")
    finally:
        sup.stop()
        if synth_proc is not None:
            synth_proc.stop()


if __name__ == "__main__":
    main()
