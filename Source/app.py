from __future__ import annotations

import os
import sys
from pathlib import Path

from .packager import find_uproject


def default_project_root() -> Path | None:
    candidates = [Path.cwd()]
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent)
    for candidate in candidates:
        try:
            find_uproject(candidate)
            return candidate.resolve()
        except ValueError:
            continue
    return None


def _configure_windows_console() -> None:
    if os.name != "nt":
        return
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and stream.isatty() and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def _hide_packaged_console() -> None:
    if os.name != "nt" or not getattr(sys, "frozen", False) or os.environ.get("UEPM_DEBUG_CONSOLE") == "1":
        return
    import ctypes

    console = ctypes.windll.kernel32.GetConsoleWindow()
    if console:
        ctypes.windll.user32.ShowWindow(console, 0)


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments:
        _configure_windows_console()
        from .cli import main as cli_main
        try:
            return cli_main(arguments, default_project_root())
        except (OSError, RuntimeError, ValueError) as error:
            print(f"错误：{error}", file=sys.stderr)
            return 2
    _hide_packaged_console()
    from .gui import run_gui
    return run_gui(default_project_root())
