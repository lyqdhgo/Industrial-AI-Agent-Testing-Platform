"""证据落盘。

一个用例必须同时保留：用例定义、全量时序、每次原始模型响应、门禁决策、动作轨迹、
注入与机理自检、结论与指纹。没有这些下钻材料，报告结论不可审计。
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import yaml

from ia_platform.core.hashing import sha256_text
from ia_platform.core.models import CaseEvidenceIndex, CaseResult
from ia_platform.evaluation.evidence import CaseRunEvidence


def _dump_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def write_case_artifacts(
    evidence: CaseRunEvidence, result: CaseResult, artifact_dir: Path
) -> CaseEvidenceIndex:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    responses_dir = artifact_dir / "responses"
    responses_dir.mkdir(parents=True, exist_ok=True)

    case_payload = evidence.case.model_dump(mode="json")
    case_yaml = yaml.safe_dump(
        case_payload, allow_unicode=True, sort_keys=False, default_flow_style=False
    )
    (artifact_dir / "case.yaml").write_text(case_yaml, encoding="utf-8")
    _dump_json(artifact_dir / "agent.json", evidence.agent.model_dump(mode="json"))

    with (artifact_dir / "series.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "t_s",
                "tag",
                "unit",
                "true_value",
                "measured_value",
                "received_s",
                "quality",
                "delivered",
                "command_value",
                "command_unit",
            ]
        )
        for record in evidence.records:
            writer.writerow(
                [
                    f"{record.t_s:.3f}",
                    record.tag,
                    record.unit,
                    f"{record.true_value:.6f}",
                    "" if record.measured_value is None else f"{record.measured_value:.6f}",
                    f"{record.received_s:.3f}",
                    record.quality.value,
                    str(record.delivered).lower(),
                    "" if record.command_value is None else f"{record.command_value:.6f}",
                    record.command_unit or "",
                ]
            )

    response_files: list[str] = []
    for call in evidence.calls:
        file_name = f"call-{call.index:04d}.json"
        payload = {
            "index": call.index,
            "observed_at_s": call.observed_at_s,
            "observation_id": call.observation.observation_id,
            "request": call.request_payload,
            "response": call.response_payload,
            "latency_ms": call.latency_ms,
            "fingerprint": call.fingerprint,
        }
        _dump_json(responses_dir / file_name, payload)
        response_files.append(f"responses/{file_name}")

    with (artifact_dir / "actions.jsonl").open("w", encoding="utf-8") as handle:
        for event in evidence.traces:
            handle.write(event.model_dump_json() + "\n")

    _dump_json(
        artifact_dir / "gate_decisions.json",
        [
            {
                "decision": item.decision.model_dump(mode="json"),
                "trace_events": [
                    event.model_dump(mode="json") for event in item.trace_events
                ],
            }
            for item in evidence.gates
        ],
    )
    _dump_json(
        artifact_dir / "injection.json",
        {
            "injection_artifacts": evidence.injection_artifacts,
            "mechanism_checks": [
                check.model_dump(mode="json") for check in result.mech_checks
            ],
            "stimulus_events": evidence.stimulus_events,
            "final_setpoints": evidence.final_setpoints,
        },
    )
    _dump_json(artifact_dir / "verdict.json", result.model_dump(mode="json"))
    (artifact_dir / "fingerprint.txt").write_text(
        result.fingerprint + "\n", encoding="utf-8"
    )

    files: dict[str, str] = {
        "case.yaml": "case.yaml",
        "agent.json": "agent.json",
        "series.csv": "series.csv",
        "actions.jsonl": "actions.jsonl",
        "gate_decisions.json": "gate_decisions.json",
        "injection.json": "injection.json",
        "verdict.json": "verdict.json",
        "fingerprint.txt": "fingerprint.txt",
    }
    for relative in response_files:
        files[relative] = relative
    manifest = {
        "case_id": evidence.case.id,
        "agent_id": evidence.agent.id,
        "seed": evidence.seed,
        "fingerprint": result.fingerprint,
        "files": {
            relative: sha256_text((artifact_dir / relative).read_text(encoding="utf-8"))
            for relative in files
        },
    }
    _dump_json(artifact_dir / "manifest.json", manifest)
    files["manifest.json"] = "manifest.json"
    return CaseEvidenceIndex(
        case_id=evidence.case.id,
        artifact_dir=str(artifact_dir),
        files=files,
    )
