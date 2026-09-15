from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Source.config_store import ProjectConfigStore
from Source import app
from Source.models import CONFIGURATIONS, CopyRule
from Source.packager import PackageRunner, build_command, clean_existing_package, copy_rule, validate_target_directory


kernel32 = SimpleNamespace(GetConsoleWindow=Mock(return_value=123))
user32 = SimpleNamespace(ShowWindow=Mock())
fake_ctypes = SimpleNamespace(windll=SimpleNamespace(kernel32=kernel32, user32=user32))
with (
    patch.object(app.os, "name", "nt"),
    patch.object(app.sys, "frozen", True, create=True),
    patch.dict(app.os.environ, {"UEPM_DEBUG_CONSOLE": "0"}),
    patch.dict(sys.modules, {"ctypes": fake_ctypes}),
):
    app._hide_packaged_console()
kernel32.GetConsoleWindow.assert_called_once_with()
user32.ShowWindow.assert_called_once_with(123, 0)


def make_project(root: Path, name: str, with_data: bool = True) -> Path:
    project = root / name
    project.mkdir()
    (project / f"{name}.uproject").write_text(json.dumps({"EngineAssociation": "5.7"}), encoding="utf-8")
    if with_data:
        (project / "Data").mkdir()
    return project


with tempfile.TemporaryDirectory() as raw:
    root = Path(raw).resolve()
    project_a = make_project(root, "Project & A")
    project_b = make_project(root, "ProjectB", with_data=False)
    store = ProjectConfigStore(root / "LocalConfig")
    config_a = store.load(project_a)
    config_b = store.load(project_b)
    assert not config_a.copy_rules and not config_b.copy_rules
    assert store.path_for(project_a) != store.path_for(project_b)
    config_a.output_directory = str(root / "OutputA")
    config_b.output_directory = str(root / "OutputB")
    store.save(config_a)
    store.save(config_b)
    assert store.load(project_a).output_directory.endswith("OutputA")
    assert store.load(project_b).output_directory.endswith("OutputB")
    shutil.copy2(store.path_for(project_a), store.path_for(project_b))
    try:
        store.load(project_b)
        raise AssertionError("跨项目配置必须被拒绝")
    except ValueError:
        pass
    store.save(config_b)
    engine = root / "UE Test 5.7"
    run_uat = engine / "Engine" / "Build" / "BatchFiles" / "RunUAT.bat"
    run_uat.parent.mkdir(parents=True)
    run_uat.touch()
    config_a.engine_root = str(engine)
    for configuration in CONFIGURATIONS:
        config_a.configuration = configuration
        command, project_file = build_command(config_a)
        assert project_file.name == "Project & A.uproject"
        assert f"-clientconfig={configuration}" in command
        assert ("-compressed" in command) == (configuration == "Shipping")
        assert str(root / "OutputA") in command

    source = project_a / "Extra"
    source.mkdir()
    (source / "keep.txt").write_text("ok", encoding="utf-8")
    (source / ".trash").mkdir()
    (source / ".trash" / "skip.txt").write_text("skip", encoding="utf-8")
    package_root = root / "Package"
    files, size = copy_rule(project_a, package_root, CopyRule("Extra", "Extras"))
    assert files == 1 and size == 2
    assert (package_root / "Extras" / "Extra" / "keep.txt").read_text(encoding="utf-8") == "ok"
    assert not (package_root / "Extras" / "Extra" / ".trash").exists()

    fake_output = root / "FakeOutput"
    run_uat.write_text(
        "@echo off\n"
        f'mkdir "{fake_output / "Windows"}"\n'
        f'type nul > "{fake_output / "Windows" / "Project & A.exe"}"\n'
        "exit /b 0\n",
        encoding="utf-8",
    )
    config_a.output_directory = str(fake_output)
    config_a.configuration = "Shipping"
    config_a.copy_rules = [CopyRule("Extra", "Extras")]
    old_output = root / "PreviousOutput" / "Windows"
    old_output.mkdir(parents=True)
    (old_output / "Project & A.exe").touch()
    (old_output / "must-remain.txt").write_text("old", encoding="utf-8")
    current_old_package = fake_output / "Windows"
    current_old_package.mkdir(parents=True)
    (current_old_package / "Project & A.exe").touch()
    (current_old_package / "stale.txt").write_text("stale", encoding="utf-8")
    assert clean_existing_package(config_a) == current_old_package
    assert not current_old_package.exists()
    assert (old_output / "must-remain.txt").is_file()
    completed_root = PackageRunner().run(config_a, on_output=print)
    assert completed_root == fake_output / "Windows"
    assert (completed_root / "Extras" / "Extra" / "keep.txt").is_file()

    try:
        validate_target_directory("../escape")
        raise AssertionError("路径越界必须被拒绝")
    except ValueError:
        pass

print("package-manager: ok")
