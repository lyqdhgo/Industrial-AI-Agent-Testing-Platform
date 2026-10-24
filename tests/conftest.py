"""测试夹具：全部使用临时数据库与证据目录，绝不触碰演示数据。"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from ia_platform.config import Settings
from ia_platform.core.catalog import PlatformCatalog
from ia_platform.core.domain import load_domain
from ia_platform.core.models import DomainPack
from ia_platform.services.context import PlatformContext


@pytest.fixture(scope="session")
def base_settings() -> Settings:
    return Settings.load()


@pytest.fixture(scope="session")
def domain(base_settings: Settings) -> DomainPack:
    return load_domain(base_settings.domain_dir)


@pytest.fixture()
def settings(tmp_path: Path, base_settings: Settings) -> Settings:
    resolved = replace(
        base_settings,
        data_dir=(tmp_path / "data").resolve(),
        artifact_dir=(tmp_path / "artifacts").resolve(),
        auto_seed=False,
        reproducibility_check=False,
    )
    resolved.ensure_directories()
    return resolved


@pytest.fixture()
def context(settings: Settings) -> PlatformContext:
    return PlatformContext.build(settings, reproducibility_check=False)


@pytest.fixture()
def catalog(context: PlatformContext) -> PlatformCatalog:
    return context.catalog
