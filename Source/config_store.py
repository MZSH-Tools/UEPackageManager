from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from platformdirs import user_config_path

from .models import ProjectConfig
from .packager import find_uproject


class ProjectConfigStore:
    """每个 .uproject 使用独立文件，禁止跨项目复用打包配置。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or user_config_path("UEPackageManager", appauthor=False, ensure_exists=False) / "Projects").resolve()

    @staticmethod
    def project_key(project_root: Path) -> str:
        project_file = find_uproject(project_root)
        normalized = os.path.normcase(str(project_file.resolve())).replace("\\", "/")
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]

    def path_for(self, project_root: Path) -> Path:
        return self.root / self.project_key(project_root) / "config.json"

    def default_config(self, project_root: Path) -> ProjectConfig:
        root = project_root.resolve()
        return ProjectConfig(
            project_root=str(root),
            output_directory=str(root / "Packages"),
            copy_rules=[],
        )

    def load(self, project_root: Path) -> ProjectConfig:
        root = project_root.resolve()
        path = self.path_for(root)
        if not path.is_file():
            return self.default_config(root)
        with path.open("r", encoding="utf-8-sig") as stream:
            data = json.load(stream)
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ValueError(f"不支持的项目配置格式：{path}")
        config = ProjectConfig.from_dict(data.get("config", {}))
        if os.path.normcase(str(config.root_path)) != os.path.normcase(str(root)):
            raise ValueError(f"项目配置身份不匹配，拒绝跨项目使用：{path}")
        return config

    def save(self, config: ProjectConfig) -> Path:
        root = config.root_path
        find_uproject(root)
        path = self.path_for(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": 1, "project_key": self.project_key(root), "config": config.to_dict()}
        self._write_json(path, payload)
        return path

    @staticmethod
    def _write_json(path: Path, payload: dict[str, object]) -> None:
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", newline="\n", prefix=".config.", suffix=".tmp", dir=path.parent, delete=False
            ) as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                temporary = Path(stream.name)
            os.replace(temporary, path)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()
