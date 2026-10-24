"""平台服务上下文：统一装配目录、领域包、仓储与服务。"""

from __future__ import annotations

from dataclasses import dataclass

from ia_platform.config import Settings
from ia_platform.core.catalog import PlatformCatalog, load_catalog
from ia_platform.core.domain import load_domain
from ia_platform.core.models import DomainPack
from ia_platform.report.service import ReportService
from ia_platform.services.baseline_service import BaselineService
from ia_platform.services.repository import Repository
from ia_platform.services.run_service import RunService
from ia_platform.services.seed_service import SeedService


@dataclass(frozen=True)
class PlatformContext:
    settings: Settings
    catalog: PlatformCatalog
    domain: DomainPack
    repository: Repository
    run_service: RunService
    baseline_service: BaselineService
    report_service: ReportService
    seed_service: SeedService

    @classmethod
    def build(
        cls,
        settings: Settings | None = None,
        *,
        reproducibility_check: bool | None = None,
    ) -> PlatformContext:
        resolved = settings or Settings.load()
        resolved.ensure_directories()
        domain = load_domain(resolved.domain_dir)
        catalog = load_catalog(resolved, domain)
        repository = Repository(resolved.db_path)
        repository.initialize()
        run_service = RunService(
            resolved,
            catalog,
            domain,
            repository,
            reproducibility_check=(
                resolved.reproducibility_check
                if reproducibility_check is None
                else reproducibility_check
            ),
        )
        baseline_service = BaselineService(repository)
        report_service = ReportService(repository)
        seed_service = SeedService(
            resolved,
            catalog,
            domain,
            repository,
            run_service,
            baseline_service,
            report_service,
        )
        return cls(
            settings=resolved,
            catalog=catalog,
            domain=domain,
            repository=repository,
            run_service=run_service,
            baseline_service=baseline_service,
            report_service=report_service,
            seed_service=seed_service,
        )
