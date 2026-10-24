"""运行配置。所有路径解析为绝对路径，避免工作目录影响可复现性。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    project_root: Path = field(
        default_factory=lambda: Path(__file__).resolve().parents[2]
    )
    data_dir: Path = field(default_factory=lambda: Path())
    artifact_dir: Path = field(default_factory=lambda: Path())
    domain_dir: Path = field(default_factory=lambda: Path())
    cases_dir: Path = field(default_factory=lambda: Path())
    agents_file: Path = field(default_factory=lambda: Path())
    suites_dir: Path = field(default_factory=lambda: Path())
    auto_seed: bool = True
    reproducibility_check: bool = True
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")

    @classmethod
    def load(cls) -> Settings:
        root = Path(__file__).resolve().parents[2]
        data_dir = Path(os.getenv("IATP_DATA_DIR", str(root / "data")))
        artifact_dir = Path(os.getenv("IATP_ARTIFACT_DIR", str(root / "artifacts")))
        domain_dir = Path(os.getenv("IATP_DOMAIN_DIR", str(root / "domain" / "demo_reactor")))
        cases_dir = Path(os.getenv("IATP_CASES_DIR", str(root / "cases")))
        agents_file = Path(os.getenv("IATP_AGENTS_FILE", str(root / "agents" / "agents.yaml")))
        suites_dir = Path(os.getenv("IATP_SUITES_DIR", str(root / "suites")))
        cors_raw = os.getenv("IATP_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
        return cls(
            project_root=root,
            data_dir=data_dir.resolve(),
            artifact_dir=artifact_dir.resolve(),
            domain_dir=domain_dir.resolve(),
            cases_dir=cases_dir.resolve(),
            agents_file=agents_file.resolve(),
            suites_dir=suites_dir.resolve(),
            auto_seed=_env_bool("IATP_AUTO_SEED", True),
            reproducibility_check=_env_bool("IATP_REPRODUCIBILITY_CHECK", True),
            cors_origins=tuple(part.strip() for part in cors_raw.split(",") if part.strip()),
        )

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "iatp.db"
