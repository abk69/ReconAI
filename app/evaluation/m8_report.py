"""Human-readable and structured M8.7 evaluation reports."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.evaluation.m8_metrics import M8MetricReport, report_to_dict


def format_cli_report(report: M8MetricReport) -> str:
    lines = [
        "M8 Resolution Evaluation",
        f"Dataset: {report.dataset}",
        f"Cases: {report.case_count}",
        "",
        "Offline deterministic harness validation",
        "(These numbers do NOT represent real Gemini production quality.)",
        "",
        f"Plan validity: {report.plan_validity_rate}%",
        f"Action allowlist compliance: {report.action_allowlist_compliance}%",
        f"Forbidden-action rate: {report.forbidden_action_rate}%",
        f"Parameter validity: {report.parameter_validity_rate}%",
        f"Expected-action coverage: {report.expected_action_coverage}%",
        f"Unsafe-plan rate: {report.unsafe_plan_rate}%",
        f"Abstention accuracy: {report.abstention_accuracy}%",
        f"Grounding adherence: {report.grounding_adherence}%",
        f"Approval bypass rate: {report.approval_bypass_rate}%",
        f"Idempotency correctness: {report.idempotency_correctness}%",
        f"Immutability correct: {report.immutability_correct}",
        f"Audit chain correct: {report.audit_chain_correct}",
        f"Audit failure chain correct: {report.audit_failure_chain_correct}",
    ]
    if report.failed_cases:
        lines.append("")
        lines.append(f"Failed cases: {', '.join(report.failed_cases)}")
    if report.safety_failures:
        lines.append(f"Safety failures: {', '.join(report.safety_failures)}")
    return "\n".join(lines)


def structured_report(report: M8MetricReport) -> dict[str, Any]:
    payload = report_to_dict(report)
    payload["timestamp"] = datetime.now(UTC).isoformat()
    return payload
