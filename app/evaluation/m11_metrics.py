"""Field, line, and document metrics. Denominators are counted, not implied."""

from __future__ import annotations

from typing import Any

from app.evaluation.m11_normalize import (
    CURRENCY_FIELDS,
    DATE_FIELDS,
    DECIMAL_FIELDS,
    HEADER_FIELDS,
    IDENTIFIER_FIELDS,
    LINE_FIELDS,
    NAME_FIELDS,
    decimals_equal,
    display,
    normalize_currency,
    normalize_date,
    normalize_identifier,
    normalize_name,
)
from app.evaluation.m11_schema import (
    CaseMetrics,
    CaseResult,
    ErrorCategory,
    EvalCase,
    FieldError,
    GroundTruthLine,
)
from app.evaluation.metrics import ratio


def _ratio_text(numerator: int, denominator: int) -> str:
    return str(ratio(numerator, denominator))


def _present(value: Any) -> bool:
    if value is None:
        return False
    return not (isinstance(value, str) and not value.strip())


def _header_value(record: Any, field: str) -> Any:
    if record is None:
        return None
    if isinstance(record, dict):
        return record.get(field)
    return getattr(record, field, None)


def _line_value(line: Any, field: str) -> Any:
    if not isinstance(line, dict):
        return None
    if field == "item_identifier":
        return line.get("item_identifier", line.get("reference"))
    return line.get(field)


def _expected_lines(case: EvalCase) -> list[dict[str, Any]]:
    return [line.model_dump() for line in case.ground_truth.lines]


def _predicted_lines(prediction: dict[str, Any] | None) -> list[Any]:
    if not isinstance(prediction, dict):
        return []
    lines = prediction.get("lines")
    if not isinstance(lines, list):
        return []
    return lines


def _compare_value(field: str, expected: Any, predicted: Any) -> ErrorCategory | None:
    if field in DECIMAL_FIELDS:
        if decimals_equal(expected, predicted):
            return None
        left = display(expected)
        right = display(predicted)
        names_match = normalize_name(left) == normalize_name(right)
        if left is not None and right is not None and left != right and names_match:
            return ErrorCategory.NORMALIZATION_MISMATCH
        return ErrorCategory.NUMERIC_MISMATCH
    if field in DATE_FIELDS:
        left = normalize_date(expected)
        right = normalize_date(predicted)
        if left is not None and right is not None and left == right:
            return None
        return ErrorCategory.DATE_MISMATCH
    if field in CURRENCY_FIELDS:
        if normalize_currency(expected) == normalize_currency(predicted):
            return None
        return ErrorCategory.INCORRECT_FIELD
    if field in IDENTIFIER_FIELDS:
        if normalize_identifier(expected) == normalize_identifier(predicted):
            return None
        if normalize_name(expected) == normalize_name(predicted):
            return ErrorCategory.NORMALIZATION_MISMATCH
        return ErrorCategory.INCORRECT_FIELD
    if field in NAME_FIELDS:
        if normalize_name(expected) == normalize_name(predicted):
            return None
        return ErrorCategory.INCORRECT_FIELD
    if normalize_identifier(expected) == normalize_identifier(predicted):
        return None
    return ErrorCategory.INCORRECT_FIELD


def _line_key(line: Any) -> tuple[str, str] | None:
    identifier = normalize_identifier(_line_value(line, "item_identifier"))
    if identifier:
        return ("id", identifier)
    name = normalize_name(_line_value(line, "description"))
    if name:
        return ("desc", name)
    return None


def _match_lines(
    expected: list[dict[str, Any]], predicted: list[Any]
) -> tuple[list[tuple[dict[str, Any], Any]], list[dict[str, Any]], list[Any]]:
    unused = list(enumerate(predicted))
    matched: list[tuple[dict[str, Any], Any]] = []
    missing: list[dict[str, Any]] = []
    for exp in expected:
        key = _line_key(exp)
        found = None
        if key is not None:
            for index, (position, pred) in enumerate(unused):
                if _line_key(pred) == key:
                    found = position
                    unused.pop(index)
                    break
        if found is None:
            missing.append(exp)
        else:
            matched.append((exp, predicted[found]))
    extra = [pred for _, pred in unused]
    return matched, missing, extra


def evaluate_prediction(
    case: EvalCase,
    prediction: dict[str, Any] | None,
    detected_type: str | None,
) -> CaseResult:
    errors: list[FieldError] = []
    prediction = prediction if isinstance(prediction, dict) else None
    expected_header = {
        field: _header_value(case.ground_truth, field)
        for field in HEADER_FIELDS
        if _present(_header_value(case.ground_truth, field))
    }
    predicted_header_present = prediction is not None and any(
        _present(prediction.get(field)) for field in HEADER_FIELDS
    )
    predicted_lines = _predicted_lines(prediction)
    if prediction is None or (not predicted_header_present and not predicted_lines):
        errors.append(
            FieldError(
                case_id=case.case_id,
                field="document",
                expected=case.document_type.value,
                predicted=None,
                category=ErrorCategory.EMPTY_EXTRACTION,
            )
        )

    header_correct = 0
    header_missing = 0
    header_incorrect = 0
    for field, expected in expected_header.items():
        predicted = prediction.get(field) if prediction else None
        if not _present(predicted):
            header_missing += 1
            errors.append(
                FieldError(
                    case_id=case.case_id,
                    field=field,
                    expected=display(expected),
                    predicted=None,
                    category=ErrorCategory.MISSING_FIELD,
                )
            )
            continue
        category = _compare_value(field, expected, predicted)
        if category is None:
            header_correct += 1
            continue
        header_incorrect += 1
        errors.append(
            FieldError(
                case_id=case.case_id,
                field=field,
                expected=display(expected),
                predicted=display(predicted),
                category=category,
            )
        )

    header_unexpected = 0
    if prediction:
        for field in HEADER_FIELDS:
            if field in expected_header:
                continue
            if _present(prediction.get(field)):
                header_unexpected += 1
                errors.append(
                    FieldError(
                        case_id=case.case_id,
                        field=field,
                        expected=None,
                        predicted=display(prediction.get(field)),
                        category=ErrorCategory.UNEXPECTED_FIELD,
                    )
                )

    if detected_type is not None and detected_type != case.ground_truth.document_type.value:
        errors.append(
            FieldError(
                case_id=case.case_id,
                field="document_type",
                expected=case.ground_truth.document_type.value,
                predicted=detected_type,
                category=ErrorCategory.DOCUMENT_TYPE_MISMATCH,
            )
        )

    expected_lines = _expected_lines(case)
    matched, missing_lines, extra_lines = _match_lines(expected_lines, predicted_lines)
    for exp in missing_lines:
        errors.append(
            FieldError(
                case_id=case.case_id,
                field="lines",
                expected=display(
                    _line_value(exp, "description") or _line_value(exp, "item_identifier")
                ),
                predicted=None,
                category=ErrorCategory.MISSING_LINE,
            )
        )
    for pred in extra_lines:
        errors.append(
            FieldError(
                case_id=case.case_id,
                field="lines",
                expected=None,
                predicted=display(
                    _line_value(pred, "description") or _line_value(pred, "item_identifier")
                ),
                category=ErrorCategory.EXTRA_LINE,
            )
        )

    line_fields_expected = 0
    line_fields_comparable = 0
    line_fields_correct = 0
    line_fields_incorrect = 0
    for exp in expected_lines:
        for field in LINE_FIELDS:
            if _present(_line_value(exp, field)):
                line_fields_expected += 1
    for exp, pred in matched:
        for field in LINE_FIELDS:
            if _present(_line_value(exp, field)):
                line_fields_comparable += 1
        for field in LINE_FIELDS:
            expected = _line_value(exp, field)
            if not _present(expected):
                continue
            predicted = _line_value(pred, field)
            label = f"lines.{field}"
            if not _present(predicted):
                line_fields_incorrect += 1
                errors.append(
                    FieldError(
                        case_id=case.case_id,
                        field=label,
                        expected=display(expected),
                        predicted=None,
                        category=ErrorCategory.LINE_FIELD_MISMATCH,
                    )
                )
                continue
            category = _compare_value(field, expected, predicted)
            if category is None:
                line_fields_correct += 1
                continue
            line_fields_incorrect += 1
            mapped = (
                ErrorCategory.LINE_FIELD_MISMATCH
                if category is not ErrorCategory.NUMERIC_MISMATCH
                else ErrorCategory.NUMERIC_MISMATCH
            )
            errors.append(
                FieldError(
                    case_id=case.case_id,
                    field=label,
                    expected=display(expected),
                    predicted=display(predicted),
                    category=mapped,
                )
            )

    header_expected = len(expected_header)
    header_comparable = header_correct + header_incorrect
    exact = not errors
    blocking = {
        ErrorCategory.MISSING_FIELD,
        ErrorCategory.INCORRECT_FIELD,
        ErrorCategory.NUMERIC_MISMATCH,
        ErrorCategory.DATE_MISMATCH,
        ErrorCategory.MISSING_LINE,
        ErrorCategory.EXTRA_LINE,
        ErrorCategory.LINE_FIELD_MISMATCH,
        ErrorCategory.DOCUMENT_TYPE_MISMATCH,
        ErrorCategory.EMPTY_EXTRACTION,
        ErrorCategory.NORMALIZATION_MISMATCH,
    }
    success = not any(error.category in blocking for error in errors)
    metrics = CaseMetrics(
        header_expected=header_expected,
        header_correct=header_correct,
        header_missing=header_missing,
        header_incorrect=header_incorrect,
        header_unexpected=header_unexpected,
        header_accuracy=_ratio_text(header_correct, header_comparable),
        header_accuracy_numerator=header_correct,
        header_accuracy_denominator=header_comparable,
        header_completeness=_ratio_text(header_correct, header_expected),
        header_completeness_numerator=header_correct,
        header_completeness_denominator=header_expected,
        line_expected_count=len(expected_lines),
        line_predicted_count=len(predicted_lines),
        line_count_match=len(expected_lines) == len(predicted_lines),
        lines_matched=len(matched),
        lines_missing=len(missing_lines),
        lines_extra=len(extra_lines),
        line_fields_expected=line_fields_expected,
        line_fields_correct=line_fields_correct,
        line_fields_incorrect=line_fields_incorrect,
        line_accuracy=_ratio_text(line_fields_correct, line_fields_comparable),
        line_accuracy_numerator=line_fields_correct,
        line_accuracy_denominator=line_fields_comparable,
        line_completeness=_ratio_text(line_fields_correct, line_fields_expected),
        line_completeness_numerator=line_fields_correct,
        line_completeness_denominator=line_fields_expected,
        exact_match=exact,
        success=success,
    )
    return CaseResult(
        case_id=case.case_id,
        document_type=case.document_type,
        passed=exact,
        metrics=metrics,
        errors=errors,
    )


def empty_ground_line() -> GroundTruthLine:
    return GroundTruthLine()
