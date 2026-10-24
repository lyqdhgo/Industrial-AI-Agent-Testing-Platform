"""SQLite 持久化。

运行时、基线与回归报告均以 Pydantic JSON 完整入库；数据库只是证据索引，
不是评测逻辑的一部分。每次操作独立连接，避免 FastAPI 多线程共享连接。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from ia_platform.core.models import BaselineRecord, RegressionReport, RunRecord


class Repository:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    suite_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_runs_created
                    ON runs(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_runs_suite_agent
                    ON runs(suite_id, agent_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS baselines (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_baselines_created
                    ON baselines(created_at DESC);

                CREATE TABLE IF NOT EXISTS regressions (
                    id TEXT PRIMARY KEY,
                    baseline_id TEXT NOT NULL,
                    candidate_run_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_regressions_created
                    ON regressions(created_at DESC);
                """
            )

    # ------------------------------------------------------------------
    # Runs
    # ------------------------------------------------------------------

    def save_run(self, run: RunRecord) -> None:
        payload = run.model_dump_json()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runs (id, suite_id, agent_id, status, created_at, payload)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    suite_id = excluded.suite_id,
                    agent_id = excluded.agent_id,
                    status = excluded.status,
                    created_at = excluded.created_at,
                    payload = excluded.payload
                """,
                (
                    run.id,
                    run.suite_id,
                    run.agent_id,
                    run.status.value,
                    run.created_at.isoformat(),
                    payload,
                ),
            )

    def get_run(self, run_id: str) -> RunRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
        return None if row is None else RunRecord.model_validate_json(row["payload"])

    def list_runs(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        suite_id: str | None = None,
        agent_id: str | None = None,
    ) -> list[RunRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if suite_id:
            clauses.append("suite_id = ?")
            params.append(suite_id)
        if agent_id:
            clauses.append("agent_id = ?")
            params.append(agent_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([max(1, min(limit, 200)), max(0, offset)])
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT payload FROM runs {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                params,
            ).fetchall()
        return [RunRecord.model_validate_json(row["payload"]) for row in rows]

    def count_runs(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM runs").fetchone()
        return int(row["count"])

    def delete_run(self, run_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM runs WHERE id = ?", (run_id,))
        return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Baselines
    # ------------------------------------------------------------------

    def save_baseline(self, baseline: BaselineRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO baselines (id, run_id, created_at, payload)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET payload = excluded.payload
                """,
                (
                    baseline.id,
                    baseline.run_id,
                    baseline.created_at.isoformat(),
                    baseline.model_dump_json(),
                ),
            )

    def get_baseline(self, baseline_id: str) -> BaselineRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM baselines WHERE id = ?", (baseline_id,)
            ).fetchone()
        return (
            None
            if row is None
            else BaselineRecord.model_validate_json(row["payload"])
        )

    def list_baselines(self, limit: int = 50) -> list[BaselineRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM baselines ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 200)),),
            ).fetchall()
        return [
            BaselineRecord.model_validate_json(row["payload"]) for row in rows
        ]

    def latest_baseline(self) -> BaselineRecord | None:
        items = self.list_baselines(limit=1)
        return items[0] if items else None

    # ------------------------------------------------------------------
    # Regressions
    # ------------------------------------------------------------------

    def save_regression(self, report: RegressionReport) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO regressions
                    (id, baseline_id, candidate_run_id, created_at, payload)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET payload = excluded.payload
                """,
                (
                    report.id,
                    report.baseline_id,
                    report.candidate_run_id,
                    report.created_at.isoformat(),
                    report.model_dump_json(),
                ),
            )

    def get_regression(self, report_id: str) -> RegressionReport | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM regressions WHERE id = ?", (report_id,)
            ).fetchone()
        return (
            None
            if row is None
            else RegressionReport.model_validate_json(row["payload"])
        )

    def list_regressions(self, limit: int = 50) -> list[RegressionReport]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM regressions ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 200)),),
            ).fetchall()
        return [
            RegressionReport.model_validate_json(row["payload"]) for row in rows
        ]

    def clear_all(self) -> None:
        """仅供显式 seed --force / 本地重置使用；不删除已落盘证据。"""
        with self._connect() as connection:
            connection.execute("DELETE FROM regressions")
            connection.execute("DELETE FROM baselines")
            connection.execute("DELETE FROM runs")
