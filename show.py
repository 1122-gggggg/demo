#!/usr/bin/env python3
"""展示系統的單一入口。"""
from __future__ import annotations

import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent


def use_project_python() -> None:
    candidates = (
        ROOT / ".venv" / "bin" / "python",
        ROOT / ".venv" / "Scripts" / "python.exe",
        ROOT.parent / "localization" / ".venv" / "bin" / "python",
        ROOT.parent / "localization" / ".venv" / "Scripts" / "python.exe",
    )
    current = Path(sys.executable).resolve()
    for candidate in candidates:
        if candidate.is_file() and candidate.resolve() != current:
            os.execv(
                str(candidate),
                [str(candidate), str(Path(__file__).resolve()), *sys.argv[1:]],
            )


def main() -> None:
    use_project_python()
    try:
        import cv2  # noqa: F401
        import numpy  # noqa: F401
        from PIL import Image  # noqa: F401
        import tkinter  # noqa: F401
    except ImportError as error:
        if os.name == "nt":
            instructions = (
                "py -3.12 -m venv .venv\n"
                ".\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt\n"
                ".\\.venv\\Scripts\\python.exe show.py"
            )
        else:
            instructions = (
                "python3 -m venv .venv\n"
                ".venv/bin/pip install -r requirements.txt\n"
                ".venv/bin/python show.py"
            )
        raise SystemExit(
            "展示環境尚未安裝；請先執行：\n" + instructions
        ) from error
    from 中央展示介面 import main as launch

    launch()


if __name__ == "__main__":
    main()
