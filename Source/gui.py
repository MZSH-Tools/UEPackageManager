from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QTextEdit,
    QVBoxLayout, QWidget,
)

from .config_store import ProjectConfigStore
from .models import CONFIGURATIONS, CopyRule, ProjectConfig
from .packager import (
    PackageRunner, build_command, detect_engine_root, find_existing_package_root, validate_copy_rules,
    validate_target_directory,
)


class PackageThread(QThread):
    output = Signal(str)
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, config: ProjectConfig, clean_output: bool = False) -> None:
        super().__init__()
        self.config = config
        self.clean_output = clean_output
        self.runner = PackageRunner()

    def run(self) -> None:
        try:
            package_root = self.runner.run(self.config, self.output.emit, clean_output=self.clean_output)
            self.completed.emit(str(package_root))
        except Exception as error:
            self.failed.emit(str(error))

    def cancel(self) -> None:
        self.runner.cancel()


class MainWindow(QMainWindow):
    def __init__(self, default_root: Path | None) -> None:
        super().__init__()
        self.setWindowTitle("UE 项目打包工具")
        self.resize(980, 720)
        self.store = ProjectConfigStore()
        initial_root = default_root or self.store.recent_project()
        self.config = self.store.load(initial_root) if initial_root else ProjectConfig(project_root="")
        self.worker: PackageThread | None = None
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        form = QFormLayout()
        layout.addLayout(form)
        self.project = QLineEdit()
        self.project.setReadOnly(True)
        form.addRow("项目目录", self._path_row(self.project, self._choose_project))
        self.engine = QLineEdit()
        form.addRow("UE目录", self._path_row(self.engine, self._choose_engine))
        self.output_directory = QLineEdit()
        form.addRow("输出目录", self._path_row(self.output_directory, self._choose_output))
        self.configuration = QComboBox()
        self.configuration.addItems(CONFIGURATIONS)
        form.addRow("打包类型", self.configuration)
        self.clean_output = QCheckBox("打包前清理当前输出路径中的旧包（每次单独确认）")
        form.addRow("清理旧包", self.clean_output)
        layout.addWidget(QLabel("附加文件和文件夹（目标位置相对打包根目录）"))
        self.rules = QTableWidget(0, 3)
        self.rules.setHorizontalHeaderLabels(["启用", "源文件或文件夹", "目标子目录"])
        self.rules.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.rules.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.rules.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        layout.addWidget(self.rules)
        actions = QHBoxLayout()
        add_file = QPushButton("添加文件")
        add_file.clicked.connect(self._add_file)
        actions.addWidget(add_file)
        add_directory = QPushButton("添加文件夹")
        add_directory.clicked.connect(self._add_directory)
        actions.addWidget(add_directory)
        remove = QPushButton("删除选中规则")
        remove.clicked.connect(self._remove_rule)
        actions.addWidget(remove)
        actions.addStretch()
        save = QPushButton("保存当前项目配置")
        save.clicked.connect(self._save)
        actions.addWidget(save)
        self.start = QPushButton("开始打包")
        self.start.clicked.connect(self._start)
        actions.addWidget(self.start)
        self.stop = QPushButton("停止")
        self.stop.setEnabled(False)
        self.stop.clicked.connect(self._stop)
        actions.addWidget(self.stop)
        actions.addStretch()
        layout.addLayout(actions)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)
        self._load_config(self.config)

    @staticmethod
    def _path_row(field: QLineEdit, callback) -> QWidget:
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(field)
        browse = QPushButton("选择")
        browse.clicked.connect(callback)
        row.addWidget(browse)
        return widget

    def _load_config(self, config: ProjectConfig) -> None:
        self.config = config
        self.project.setText(config.project_root)
        self.engine.setText(config.engine_root)
        self.output_directory.setText(config.output_directory)
        self.configuration.setCurrentText(config.configuration)
        self.rules.setRowCount(0)
        for rule in config.copy_rules:
            self._append_rule(rule)
        has_project = bool(config.project_root)
        self.start.setEnabled(has_project)

    def _collect_config(self) -> ProjectConfig:
        if not self.project.text().strip():
            raise ValueError("请先选择 .uproject 项目。")
        rules: list[CopyRule] = []
        for row in range(self.rules.rowCount()):
            enabled = self.rules.cellWidget(row, 0)
            source = self.rules.item(row, 1).text().strip()
            target = self.rules.item(row, 2).text().strip() or "."
            validate_target_directory(target)
            rules.append(CopyRule(source, target, isinstance(enabled, QCheckBox) and enabled.isChecked()))
        return ProjectConfig(
            project_root=str(Path(self.project.text()).resolve()), engine_root=self.engine.text().strip(),
            output_directory=str(Path(self.output_directory.text()).resolve()),
            configuration=self.configuration.currentText(), copy_rules=rules,
        )

    def _append_rule(self, rule: CopyRule) -> None:
        row = self.rules.rowCount()
        self.rules.insertRow(row)
        enabled = QCheckBox()
        enabled.setChecked(rule.enabled)
        self.rules.setCellWidget(row, 0, enabled)
        self.rules.setItem(row, 1, QTableWidgetItem(rule.source))
        self.rules.setItem(row, 2, QTableWidgetItem(rule.target_directory))

    def _choose_project(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "选择 UE 项目", self.project.text(), "UE项目 (*.uproject)")
        if filename:
            try:
                self._load_config(self.store.load(Path(filename).parent))
                self.store.remember_project(Path(filename).parent)
            except Exception as error:
                QMessageBox.critical(self, "无法切换项目", str(error))

    def _choose_engine(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择 UE 根目录", self.engine.text())
        if directory:
            self.engine.setText(directory)

    def _choose_output(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择打包输出目录", self.output_directory.text())
        if directory:
            self.output_directory.setText(directory)

    def _add_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "选择附加文件", self.config.project_root)
        if filename:
            self._append_rule(CopyRule(filename, "."))

    def _add_directory(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择附加文件夹", self.config.project_root)
        if directory:
            self._append_rule(CopyRule(directory, "."))

    def _remove_rule(self) -> None:
        for row in sorted({index.row() for index in self.rules.selectedIndexes()}, reverse=True):
            self.rules.removeRow(row)

    def _save(self) -> bool:
        try:
            config = self._collect_config()
            config.engine_root = str(detect_engine_root(config.root_path, config.engine_root))
            validate_copy_rules(config)
            build_command(config)
            path = self.store.save(config)
            self.store.remember_project(config.root_path)
            self.config = config
            self.log.append(f"配置已保存：{path}")
            return True
        except Exception as error:
            QMessageBox.critical(self, "配置无效", str(error))
            return False

    def _start(self) -> None:
        if not self._save():
            return
        if self.clean_output.isChecked():
            target = find_existing_package_root(self.config)
            if target is not None:
                answer = QMessageBox.question(
                    self,
                    "确认清理旧包",
                    f"将递归删除当前输出路径中识别到的旧包：\n{target}\n\n原来的其他输出路径不会受影响。",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if answer != QMessageBox.Yes:
                    self.log.append("已取消清理和本次打包。")
                    return
        self.start.setEnabled(False)
        self.stop.setEnabled(True)
        self.log.append("开始打包……")
        self.worker = PackageThread(self.config, self.clean_output.isChecked())
        self.worker.output.connect(self.log.append)
        self.worker.completed.connect(self._completed)
        self.worker.failed.connect(self._failed)
        self.worker.start()

    def _stop(self) -> None:
        if self.worker:
            self.worker.cancel()
            self.log.append("正在停止打包……")

    def _completed(self, package_root: str) -> None:
        self.start.setEnabled(True)
        self.stop.setEnabled(False)
        QMessageBox.information(self, "打包完成", package_root)

    def _failed(self, message: str) -> None:
        self.start.setEnabled(True)
        self.stop.setEnabled(False)
        QMessageBox.critical(self, "打包未完成", message)


def run_gui(default_root: Path | None) -> int:
    application = QApplication.instance() or QApplication([])
    application.setApplicationName("UE 项目打包工具")
    application.setStyle("Fusion")
    window = MainWindow(default_root)
    window.show()
    return application.exec()
