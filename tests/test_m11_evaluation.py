"""M11 extraction evaluation. Offline tests do not call Gemini."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domain.enums import DocumentType
from app.evaluation.m11_dataset import DATASET, DATASET_ID
from app.evaluation.m11_harness import offline_report
from app.evaluation.m11_metrics import evaluate_prediction
from app.evaluation.m11_normalize import decimals_equal, normalize_date
from app.evaluation.m11_schema import ErrorCategory, EvalCase, GroundTruth, GroundTruthLine

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _case(truth: GroundTruth, case_id: str = "unit") -> EvalCase:
    return EvalCase(
        case_id=case_id,
        document_type=truth.document_type,
        source_representation="unit",
        source_text="",
        filename="unit.pdf",
        ground_truth=truth,
        notes="unit",
        edge_conditions=["unit"],
    )


def _invoice(**kwargs: object) -> GroundTruth:
    payload: dict[str, object] = {
        "document_type": DocumentType.INVOICE,
        "invoice_number": "INV-1",
        "vendor_name": "Northwind",
    }
    payload.update(kwargs)
    return GroundTruth(**payload)  # type: ignore[arg-type]


def test_dataset_has_required_coverage() -> None:
    assert DATASET_ID == "m11_extraction_eval_v1"
    assert len(DATASET) == 20
    ids = [case.case_id for case in DATASET]
    assert len(ids) == len(set(ids))
    representations = {case.source_representation for case in DATASET}
    assert {"pdf_text", "xlsx_table", "ocr_text"} <= representations


def test_exact_header_match_and_denominators() -> None:
    truth = _invoice(invoice_date=date(2026, 9, 15), currency="USD", total_amount=Decimal("10.00"))
    result = evaluate_prediction(
        _case(truth),
        {
            "invoice_number": "INV-1",
            "vendor_name": "northwind",
            "invoice_date": "2026-09-15",
            "currency": "usd",
            "total_amount": "10",
        },
        "INVOICE",
    )
    assert result.passed
    assert result.metrics.header_expected == 5
    assert result.metrics.header_correct == 5
    assert result.metrics.header_accuracy_denominator == 5
    assert result.metrics.header_completeness_denominator == 5
    assert result.metrics.header_accuracy == "1.0000"


def test_normalized_string_and_identifier_case() -> None:
    truth = _invoice()
    folded = evaluate_prediction(
        _case(truth),
        {"invoice_number": "INV-1", "vendor_name": "  NORTHWIND  "},
        "INVOICE",
    )
    assert folded.metrics.header_correct == 2
    mismatch = evaluate_prediction(
        _case(truth),
        {"invoice_number": "inv-1", "vendor_name": "Northwind"},
        "INVOICE",
    )
    assert any(error.category is ErrorCategory.NORMALIZATION_MISMATCH for error in mismatch.errors)


def test_date_and_decimal_rules() -> None:
    assert normalize_date("15/09/2026") == date(2026, 9, 15)
    assert normalize_date("01/02/2026") is None
    assert decimals_equal("1,000.50", Decimal("1000.50"))
    assert not decimals_equal(Decimal("18"), Decimal("0.18"))
    assert not decimals_equal(1.5, Decimal("1.5"))
    truth = _invoice(invoice_date=date(2026, 9, 15), total_amount=Decimal("10.00"))
    result = evaluate_prediction(
        _case(truth),
        {
            "invoice_number": "INV-1",
            "vendor_name": "Northwind",
            "invoice_date": "01/02/2026",
            "total_amount": "10.01",
        },
        "INVOICE",
    )
    categories = {error.category for error in result.errors}
    assert ErrorCategory.DATE_MISMATCH in categories
    assert ErrorCategory.NUMERIC_MISMATCH in categories
    assert result.metrics.header_accuracy_numerator == 2
    assert result.metrics.header_accuracy_denominator == 4


def test_missing_incorrect_and_unexpected() -> None:
    truth = _invoice()
    result = evaluate_prediction(
        _case(truth),
        {"vendor_name": "Other", "currency": "USD"},
        "INVOICE",
    )
    categories = {error.field: error.category for error in result.errors}
    assert categories["invoice_number"] is ErrorCategory.MISSING_FIELD
    assert categories["vendor_name"] is ErrorCategory.INCORRECT_FIELD
    assert categories["currency"] is ErrorCategory.UNEXPECTED_FIELD
    assert result.metrics.header_missing == 1
    assert result.metrics.header_unexpected == 1
    assert result.metrics.header_completeness_denominator == 2
    assert result.metrics.header_accuracy_denominator == 1
    assert not result.metrics.success
    assert not result.passed


def test_lines_missing_extra_and_field_mismatch() -> None:
    truth = _invoice(
        lines=[
            GroundTruthLine(
                item_identifier="A",
                description="Cable",
                quantity=Decimal("2"),
                unit_price=Decimal("5"),
            ),
            GroundTruthLine(item_identifier="B", description="Bolt", quantity=Decimal("1")),
        ]
    )
    result = evaluate_prediction(
        _case(truth),
        {
            "invoice_number": "INV-1",
            "vendor_name": "Northwind",
            "lines": [
                {"reference": "A", "description": "Cable", "quantity": "9", "unit_price": "5"},
                {"reference": "C", "description": "Nut", "quantity": "1"},
            ],
        },
        "INVOICE",
    )
    categories = [error.category for error in result.errors]
    assert ErrorCategory.MISSING_LINE in categories
    assert ErrorCategory.EXTRA_LINE in categories
    assert ErrorCategory.NUMERIC_MISMATCH in categories
    assert result.metrics.lines_matched == 1
    assert result.metrics.line_accuracy_denominator == 4
    assert result.metrics.line_completeness_denominator == 7
    assert result.metrics.line_fields_correct == 3


def test_empty_and_malformed_prediction() -> None:
    truth = _invoice()
    empty = evaluate_prediction(_case(truth), None, "INVOICE")
    assert any(error.category is ErrorCategory.EMPTY_EXTRACTION for error in empty.errors)
    assert empty.metrics.header_missing == 2
    malformed = evaluate_prediction(
        _case(truth),
        {"lines": "not-a-list", "invoice_number": {"bad": 1}},
        "INVOICE",
    )
    assert malformed.metrics.header_incorrect == 1
    assert malformed.metrics.line_predicted_count == 0


def test_document_type_mismatch_fails() -> None:
    result = evaluate_prediction(
        _case(_invoice()),
        {"invoice_number": "INV-1", "vendor_name": "Northwind"},
        "PO",
    )
    assert any(error.category is ErrorCategory.DOCUMENT_TYPE_MISMATCH for error in result.errors)
    assert not result.metrics.exact_match


def test_offline_report_is_deterministic_and_has_no_live_call() -> None:
    first = offline_report()
    second = offline_report()
    assert first == second
    assert first["dataset"] == DATASET_ID
    assert first["mode"] == "OFFLINE_DETERMINISTIC_EVALUATION"
    assert first["m6_status"] == "NOT_RUN"
    assert first["comparison"][0]["m6"] is None
    assert first["regression_failures"] == []
    assert len(first["cases"]) == 20


@pytest.mark.live_llm
def test_live_clean_invoice_is_bounded() -> None:
    from app.evaluation.m11_runner import run_live

    result = run_live()
    if result["status"] == "KEY_ABSENT_LIVE_SKIPPED":
        pytest.skip("GEMINI_API_KEY is not configured")
    assert result["status"] == "OK"
    assert result["case_id"] == "clean-invoice"
    assert "api_key" not in result
    assert result["m4"]["documents"] == 1
    assert result["m6"]["documents"] == 1
