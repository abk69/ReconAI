"""Deterministic evaluator: golden expected vs M4 extracted candidate."""

from __future__ import annotations

from typing import Any

from app.domain.enums import DocumentType
from app.evaluation.metrics import ratio, values_equal
from app.evaluation.schemas import (
    EvaluationResult,
    FieldEvaluation,
    GoldenDocument,
    LineItemMetrics,
)

HEADER_FIELDS: dict[DocumentType, list[tuple[str, str]]] = {
    DocumentType.INVOICE: [
        ("invoice_number", "string"),
        ("po_number", "string"),
        ("vendor_name", "string"),
        ("invoice_date", "date"),
        ("currency", "string"),
        ("subtotal", "decimal"),
        ("tax_amount", "decimal"),
        ("total_amount", "decimal"),
    ],
    DocumentType.PO: [
        ("po_number", "string"),
        ("vendor_name", "string"),
        ("order_date", "date"),
        ("currency", "string"),
    ],
    DocumentType.GRN: [
        ("grn_number", "string"),
        ("po_number", "string"),
        ("receipt_date", "date"),
        ("vendor_name", "string"),
    ],
    DocumentType.UNKNOWN: [],
}

LINE_FIELDS: dict[DocumentType, list[tuple[str, str]]] = {
    DocumentType.INVOICE: [
        ("line_number", "string"),
        ("description", "string"),
        ("quantity", "decimal"),
        ("unit_price", "decimal"),
        ("tax_rate", "decimal"),
    ],
    DocumentType.PO: [
        ("line_number", "string"),
        ("description", "string"),
        ("quantity", "decimal"),
        ("unit_price", "decimal"),
        ("tax_rate", "decimal"),
    ],
    DocumentType.GRN: [
        ("line_number", "string"),
        ("description", "string"),
        ("quantity", "decimal"),
    ],
    DocumentType.UNKNOWN: [],
}


class ExtractionEvaluator:
    """Compare expected golden structured data against an actual candidate."""

    def evaluate(
        self,
        golden: GoldenDocument,
        actual: dict[str, Any] | None,
    ) -> EvaluationResult:
        expected = golden.expected
        actual = actual or {}
        details: list[FieldEvaluation] = []
        correct: list[str] = []
        incorrect: list[str] = []
        missing: list[str] = []

        header_specs = HEADER_FIELDS.get(golden.document_type, [])
        for field_name, kind in header_specs:
            if field_name not in expected:
                continue
            path = field_name
            exp_val = expected.get(field_name)
            act_val = actual.get(field_name)
            status = self._compare(path, exp_val, act_val, kind)
            details.append(
                FieldEvaluation(
                    field_path=path,
                    expected=exp_val,
                    actual=act_val,
                    status=status,
                )
            )
            if status == "correct":
                correct.append(path)
            elif status == "missing":
                missing.append(path)
            else:
                incorrect.append(path)

        line_metrics = self._evaluate_lines(
            document_type=golden.document_type,
            expected_lines=list(expected.get("lines") or []),
            actual_lines=list(actual.get("lines") or []),
            details=details,
            correct=correct,
            incorrect=incorrect,
            missing=missing,
        )

        evaluated = len(correct) + len(incorrect) + len(missing)
        accuracy = ratio(len(correct), evaluated)
        # Completeness: expected fields that are present (correct or incorrect).
        present = len(correct) + len(incorrect)
        expected_count = evaluated
        completeness = ratio(present, expected_count)

        overall = (
            evaluated > 0
            and len(incorrect) == 0
            and len(missing) == 0
            and (line_metrics is None or line_metrics.count_match)
        )

        return EvaluationResult(
            evaluation_id=golden.evaluation_id,
            document_type=golden.document_type,
            fields_evaluated=evaluated,
            correct_fields=correct,
            incorrect_fields=incorrect,
            missing_fields=missing,
            field_details=details,
            field_accuracy=accuracy,
            completeness=completeness,
            line_item_metrics=line_metrics,
            overall_success=overall,
            message="ok" if overall else "mismatches found",
        )

    def evaluate_many(
        self,
        pairs: list[tuple[GoldenDocument, dict[str, Any] | None]],
    ) -> list[EvaluationResult]:
        return [self.evaluate(golden, actual) for golden, actual in pairs]

    def document_success_rate(self, results: list[EvaluationResult]) -> float:
        if not results:
            return 0.0
        successes = sum(1 for r in results if r.overall_success)
        return successes / len(results)

    def _evaluate_lines(
        self,
        *,
        document_type: DocumentType,
        expected_lines: list[Any],
        actual_lines: list[Any],
        details: list[FieldEvaluation],
        correct: list[str],
        incorrect: list[str],
        missing: list[str],
    ) -> LineItemMetrics | None:
        if not expected_lines and not actual_lines:
            return None

        specs = LINE_FIELDS.get(document_type, [])
        fields_evaluated = 0
        fields_correct = 0
        count = max(len(expected_lines), len(actual_lines))

        for idx in range(count):
            exp_line = expected_lines[idx] if idx < len(expected_lines) else None
            act_line = actual_lines[idx] if idx < len(actual_lines) else None
            if not isinstance(exp_line, dict):
                continue
            for field_name, kind in specs:
                if field_name not in exp_line:
                    continue
                path = f"lines[{idx}].{field_name}"
                exp_val = exp_line.get(field_name)
                act_val = act_line.get(field_name) if isinstance(act_line, dict) else None
                status = self._compare(path, exp_val, act_val, kind)
                details.append(
                    FieldEvaluation(
                        field_path=path,
                        expected=exp_val,
                        actual=act_val,
                        status=status,
                    )
                )
                fields_evaluated += 1
                if status == "correct":
                    correct.append(path)
                    fields_correct += 1
                elif status == "missing":
                    missing.append(path)
                else:
                    incorrect.append(path)

        return LineItemMetrics(
            expected_count=len(expected_lines),
            actual_count=len(actual_lines),
            count_match=len(expected_lines) == len(actual_lines),
            fields_evaluated=fields_evaluated,
            fields_correct=fields_correct,
            field_accuracy=ratio(fields_correct, fields_evaluated),
        )

    @staticmethod
    def _compare(path: str, expected: Any, actual: Any, kind: str) -> str:
        if expected is not None and (actual is None or actual == ""):
            return "missing"
        if values_equal(expected, actual, kind=kind):
            return "correct"
        return "incorrect"
