from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


CONFIGURATIONS = ("Development", "Shipping")
PLATFORMS = ("Win64",)


@dataclass
class CopyRule:
    source: str
    target_directory: str = "."
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CopyRule":
        return cls(
            source=str(data.get("source", "")),
            target_directory=str(data.get("target_directory", ".")),
            enabled=bool(data.get("enabled", True)),
        )


@dataclass
class ProjectConfig:
    project_root: str
    engine_root: str = ""
    output_directory: str = ""
    configuration: str = "Development"
    platform: str = "Win64"
    copy_rules: list[CopyRule] = field(default_factory=list)

    @property
    def root_path(self) -> Path:
        return Path(self.project_root).resolve()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectConfig":
        return cls(
            project_root=str(data.get("project_root", "")),
            engine_root=str(data.get("engine_root", "")),
            output_directory=str(data.get("output_directory", "")),
            configuration=str(data.get("configuration", "Development")),
            platform=str(data.get("platform", "Win64")),
            copy_rules=[CopyRule.from_dict(item) for item in data.get("copy_rules", []) if isinstance(item, dict)],
        )
