from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QPushButton

from Source.config_store import ProjectConfigStore
from Source.gui import MainWindow
from Source.models import ProjectConfig


def button(window: MainWindow, text: str) -> QPushButton:
    return next(item for item in window.findChildren(QPushButton) if item.text() == text)


def wait_for_thread(application: QApplication, window: MainWindow, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while window.worker and window.worker.isRunning() and time.monotonic() < deadline:
        application.processEvents()
        time.sleep(0.02)
    application.processEvents()
    assert window.worker and not window.worker.isRunning(), "打包线程未在时限内结束"


with tempfile.TemporaryDirectory() as raw:
    root = Path(raw).resolve()
    project = root / "Project A"
    project.mkdir()
    project_file = project / "Project A.uproject"
    project_file.write_text(json.dumps({"EngineAssociation": "5.7"}), encoding="utf-8")
    second_project = root / "Project B"
    second_project.mkdir()
    second_project_file = second_project / "Project B.uproject"
    second_project_file.write_text(json.dumps({"EngineAssociation": "5.7"}), encoding="utf-8")

    engine = root / "UE Test"
    run_uat = engine / "Engine" / "Build" / "BatchFiles" / "RunUAT.bat"
    run_uat.parent.mkdir(parents=True)
    run_uat.touch()
    output = root / "Output"
    selected_output = root / "Selected Output"
    old_package = output / "Windows"
    old_package.mkdir(parents=True)
    (old_package / "Project A.exe").touch()
    (old_package / "must-remain.txt").write_text("old", encoding="utf-8")
    extra_file = root / "notice.txt"
    extra_file.write_text("file", encoding="utf-8")
    extra_directory = root / "ExtraDirectory"
    extra_directory.mkdir()
    (extra_directory / "inside.txt").write_text("directory", encoding="utf-8")

    store = ProjectConfigStore(root / "LocalConfig")
    store.save(ProjectConfig(str(project), str(engine), str(output)))
    store.save(ProjectConfig(str(second_project), str(engine), str(output)))

    application = QApplication.instance() or QApplication([])
    window = MainWindow(project)
    window.store = store
    window._load_config(store.load(project))
    window.show()
    application.processEvents()

    select_buttons = sorted(
        (item for item in window.findChildren(QPushButton) if item.text() == "选择"),
        key=lambda item: item.mapTo(window, item.rect().topLeft()).y(),
    )
    assert len(select_buttons) == 3
    with patch.object(QFileDialog, "getOpenFileName", return_value=(str(second_project_file), "")):
        select_buttons[0].click()
    assert Path(window.project.text()) == second_project
    with patch.object(QFileDialog, "getOpenFileName", return_value=(str(project_file), "")):
        select_buttons[0].click()
    assert Path(window.project.text()) == project

    with patch.object(QFileDialog, "getExistingDirectory", return_value=str(engine)):
        select_buttons[1].click()
    assert Path(window.engine.text()) == engine
    with patch.object(QFileDialog, "getExistingDirectory", return_value=str(selected_output)):
        select_buttons[2].click()
    assert Path(window.output_directory.text()) == selected_output

    with patch.object(QFileDialog, "getOpenFileName", return_value=(str(extra_file), "")):
        button(window, "添加文件").click()
    with patch.object(QFileDialog, "getExistingDirectory", return_value=str(extra_directory)):
        button(window, "添加文件夹").click()
    assert window.rules.rowCount() == 2
    window.rules.selectRow(1)
    button(window, "删除选中规则").click()
    assert window.rules.rowCount() == 1

    with patch.object(QMessageBox, "critical") as critical:
        button(window, "保存当前项目配置").click()
    critical.assert_not_called()
    saved = store.load(project)
    assert Path(saved.output_directory) == selected_output
    assert len(saved.copy_rules) == 1 and Path(saved.copy_rules[0].source) == extra_file

    run_uat.write_text(
        "@echo off\n"
        f'mkdir "{selected_output / "Windows"}"\n'
        f'type nul > "{selected_output / "Windows" / "Project A.exe"}"\n'
        "exit /b 0\n",
        encoding="utf-8",
    )
    current_old_package = selected_output / "Windows"
    current_old_package.mkdir(parents=True)
    (current_old_package / "Project A.exe").touch()
    (current_old_package / "stale.txt").write_text("stale", encoding="utf-8")
    window.clean_output.setChecked(True)
    with (
        patch.object(QMessageBox, "question", return_value=QMessageBox.Yes) as question,
        patch.object(QMessageBox, "information") as information,
        patch.object(QMessageBox, "critical") as critical,
    ):
        button(window, "开始打包").click()
        wait_for_thread(application, window)
    question.assert_called_once()
    information.assert_called_once()
    critical.assert_not_called()
    assert not (current_old_package / "stale.txt").exists()
    assert (old_package / "must-remain.txt").is_file()
    assert (selected_output / "Windows" / "notice.txt").read_text(encoding="utf-8") == "file"

    run_uat.write_text("@echo off\nping 127.0.0.1 -n 30 >nul\nexit /b 0\n", encoding="utf-8")
    window.clean_output.setChecked(False)
    with patch.object(QMessageBox, "information") as information, patch.object(QMessageBox, "critical") as critical:
        button(window, "开始打包").click()
        deadline = time.monotonic() + 5
        while window.worker and window.worker.runner._process is None and time.monotonic() < deadline:
            application.processEvents()
            time.sleep(0.02)
        assert window.worker and window.worker.runner._process is not None
        button(window, "停止").click()
        wait_for_thread(application, window)
    information.assert_not_called()
    critical.assert_called_once()
    assert "取消" in critical.call_args.args[2]
    window.close()

print("gui-buttons: ok")
