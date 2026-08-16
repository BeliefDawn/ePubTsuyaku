import ctypes
import logging
import os
import sys
import threading
import webbrowser
from pathlib import Path

from translator.webapp import build_web_parser, create_app


def _notify(message: str) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(0, message, "ePubTsuyaku", 0x10)
    except Exception:
        pass


def data_root() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "ePubTsuyaku"
        base.mkdir(parents=True, exist_ok=True)
        return base
    exe_dir = Path(sys.executable).resolve().parent
    candidates = [
        exe_dir / "data",
        Path(os.environ.get("LOCALAPPDATA", str(exe_dir))) / "EpubTsuyaku",
    ]
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".writetest"
            probe.write_text("x", encoding="utf-8")
            probe.unlink()
            return candidate
        except OSError:
            continue
    return exe_dir


def main() -> int:
    args = build_web_parser().parse_args()
    root = data_root()

    logging.basicConfig(
        filename=str(root / "app.log"),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("epubtsuyaku").info("starting with data root: %s", root)

    app = create_app(project_root=root)
    url = f"http://{args.host}:{args.port}"
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        app.run(host=args.host, port=args.port, debug=args.debug, use_reloader=False)
    except OSError as exc:
        logging.getLogger("epubtsuyaku").exception("failed to start server")
        _notify(f"无法启动服务（端口 {args.port} 可能已被占用）：\n{exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
