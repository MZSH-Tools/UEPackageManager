from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import threading
from pathlib import Path, PurePosixPath
from typing import Callable

from .models import CONFIGURATIONS, PLATFORMS, CopyRule, ProjectConfig


EXCLUDED_NAMES = {".agents", ".codex", ".git", ".idea", ".svn", ".trash", ".vs", "__pycache__"}


def _create_windows_job(process: subprocess.Popen[str]) -> int | None:
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    handle = kernel32.CreateJobObjectW(None, None)
    if not handle:
        return None
    if not kernel32.AssignProcessToJobObject(handle, wintypes.HANDLE(process._handle)):
        kernel32.CloseHandle(handle)
        return None
    return int(handle)


def _terminate_windows_job(handle: int | None) -> bool:
    if os.name != "nt" or not handle:
        return False
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateJobObject.restype = wintypes.BOOL
    return bool(kernel32.TerminateJobObject(wintypes.HANDLE(handle), 130))


def _close_windows_job(handle: int | None) -> None:
    if os.name != "nt" or not handle:
        return
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle(wintypes.HANDLE(handle))


def find_uproject(project_root: Path) -> Path:
    root = project_root.resolve()
    preferred = root / f"{root.name}.uproject"
    if preferred.is_file():
        return preferred
    projects = sorted(root.glob("*.uproject"))
    if len(projects) != 1:
        raise ValueError(f"项目目录必须且只能包含一个 .uproject：{root}")
    return projects[0]


def detect_engine_root(project_root: Path, configured: str = "") -> Path:
    if configured:
        candidate = Path(configured).resolve()
        if _run_uat(candidate).is_file():
            return candidate
        raise ValueError(f"配置的 UE 目录无效：{candidate}")

    project_file = find_uproject(project_root)
    with project_file.open("r", encoding="utf-8-sig") as stream:
        association = str(json.load(stream).get("EngineAssociation", "")).strip()
    candidates: list[Path] = []
    if association:
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        candidates.append(program_files / "Epic Games" / f"UE_{association}")
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Epic Games\Unreal Engine\Builds") as key:
                index = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, index)
                    except OSError:
                        break
                    if name == association or name.strip("{}") == association.strip("{}"):
                        candidates.append(Path(str(value)))
                    index += 1
        except OSError:
            pass
    for candidate in candidates:
        if _run_uat(candidate).is_file():
            return candidate.resolve()
    raise ValueError(f"无法定位项目 {project_file.name} 对应的 UE {association or '版本'}，请手动选择引擎目录。")


def _run_uat(engine_root: Path) -> Path:
    return engine_root / "Engine" / "Build" / "BatchFiles" / "RunUAT.bat"


def _quote_cmd_argument(value: str) -> str:
    if any(character in value for character in ('"', "\r", "\n")):
        raise ValueError(f"命令参数包含不允许的字符：{value}")
    return f'"{value}"'


def validate_target_directory(value: str) -> PurePosixPath:
    normalized = value.replace("\\", "/").strip() or "."
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts or any(":" in part for part in path.parts):
        raise ValueError(f"附加文件目标必须是包根目录内的相对目录：{value}")
    return path


def build_command(config: ProjectConfig) -> tuple[str, Path]:
    root = config.root_path
    project_file = find_uproject(root)
    if config.configuration not in CONFIGURATIONS:
        raise ValueError(f"不支持的打包类型：{config.configuration}")
    if config.platform not in PLATFORMS:
        raise ValueError(f"不支持的平台：{config.platform}")
    if not config.output_directory.strip():
        raise ValueError("请先设置打包输出目录。")
    output = Path(config.output_directory).resolve()
    if output == root:
        raise ValueError("打包输出目录不能等于项目根目录。")
    engine_root = detect_engine_root(root, config.engine_root)
    run_uat = _run_uat(engine_root)
    arguments = [
        str(run_uat), "BuildCookRun", f"-project={project_file}", "-noP4", "-utf8output", "-unattended",
        f"-platform={config.platform}", f"-clientconfig={config.configuration}", "-build", "-cook", "-stage",
        "-pak", "-archive", f"-archivedirectory={output}", "-prereqs",
    ]
    if config.configuration == "Shipping":
        arguments.append("-compressed")
    command_line = " ".join(_quote_cmd_argument(argument) for argument in arguments)
    return f'cmd.exe /d /s /c "{command_line}"', project_file


def resolve_source(project_root: Path, source: str) -> Path:
    path = Path(source)
    return path.resolve() if path.is_absolute() else (project_root / path).resolve()


def validate_copy_rules(config: ProjectConfig) -> None:
    for rule in config.copy_rules:
        if not rule.enabled:
            continue
        source = resolve_source(config.root_path, rule.source)
        if not source.exists():
            raise ValueError(f"附加文件不存在：{source}")
        validate_target_directory(rule.target_directory)


def find_package_root(output_directory: Path, project_name: str) -> Path:
    output = output_directory.resolve()
    if (output / f"{project_name}.exe").is_file():
        return output
    for name in ("Windows", "WindowsNoEditor", "Win64"):
        candidate = output / name
        if (candidate / f"{project_name}.exe").is_file():
            return candidate
    matches = [path.parent for path in output.glob(f"*/{project_name}.exe") if path.is_file()]
    if len(matches) == 1:
        return matches[0]
    raise FileNotFoundError(f"打包成功但无法在输出目录定位顶层 {project_name}.exe：{output}")


def _should_skip(path: Path) -> bool:
    return any(part in EXCLUDED_NAMES for part in path.parts) or path.suffix.lower() == ".pyc"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_rule(project_root: Path, package_root: Path, rule: CopyRule) -> tuple[int, int]:
    source = resolve_source(project_root, rule.source)
    relative_target = validate_target_directory(rule.target_directory)
    target_directory = (package_root / Path(*relative_target.parts)).resolve()
    if not target_directory.is_relative_to(package_root.resolve()):
        raise ValueError(f"附加文件目标越出包根目录：{rule.target_directory}")
    target_directory.mkdir(parents=True, exist_ok=True)
    files = 0
    total_bytes = 0
    if source.is_file():
        destinations = [(source, target_directory / source.name)]
    elif source.is_dir():
        destination_root = target_directory / source.name
        destinations = [
            (path, destination_root / path.relative_to(source))
            for path in source.rglob("*")
            if path.is_file() and not path.is_symlink() and not _should_skip(path.relative_to(source))
        ]
    else:
        raise FileNotFoundError(source)
    for original, destination in destinations:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, destination)
        if _sha256(original) != _sha256(destination):
            raise IOError(f"复制后哈希不一致：{destination}")
        files += 1
        total_bytes += destination.stat().st_size
    return files, total_bytes


class PackageRunner:
    def __init__(self) -> None:
        self._process: subprocess.Popen[str] | None = None
        self._job_handle: int | None = None
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()
        process = self._process
        if process and process.poll() is None:
            _terminate_windows_job(self._job_handle)
            if process.poll() is None:
                process.kill()

    def run(self, config: ProjectConfig, on_output: Callable[[str], None] = print, copy_extras: bool = True) -> Path:
        command, project_file = build_command(config)
        if copy_extras:
            validate_copy_rules(config)
        on_output("执行命令：" + command)
        self._cancelled.clear()
        process = subprocess.Popen(
            command, cwd=config.root_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        self._job_handle = _create_windows_job(process)
        self._process = process
        try:
            assert process.stdout is not None
            for line in process.stdout:
                on_output(line.rstrip())
            return_code = process.wait()
        finally:
            _close_windows_job(self._job_handle)
            self._job_handle = None
        if self._cancelled.is_set():
            raise RuntimeError("打包已取消。")
        if return_code != 0:
            raise RuntimeError(f"UE 打包失败，退出码：{return_code}")
        package_root = find_package_root(Path(config.output_directory), project_file.stem)
        if copy_extras:
            for rule in config.copy_rules:
                if not rule.enabled:
                    continue
                files, total_bytes = copy_rule(config.root_path, package_root, rule)
                on_output(f"已复制 {rule.source}：{files} 个文件，{total_bytes} 字节")
        on_output(f"打包完成：{package_root}")
        return package_root
