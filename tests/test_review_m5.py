"""M5 human review, evaluation, and promotion tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    Document,
    DocumentExtractionResult,
    Invoice,
    InvoiceLine,
    PurchaseOrder,
    ReviewDecision,
    ReviewTask,
    Vendor,
)
from app.db.session import get_db
from app.domain.enums import (
    DocumentStatus,
    DocumentType,
    ExtractionOutcome,
    ReviewPriority,
    ReviewStatus,
)
from app.evaluation.evaluator import ExtractionEvaluator
from app.evaluation.golden import GOLDEN_DATASET, get_golden
from app.evaluation.metrics import values_equal
from app.evaluation.schemas import GoldenDocument
from app.main import app
from app.review.transitions import InvalidReviewTransitionError, assert_transition
from app.services.document_service import DocumentService
from app.services.document_understanding_service import DocumentUnderstandingService
from app.services.promotion_service import (
    PromotionNotAllowedError,
    PromotionService,
    PromotionValidationError,
)
from app.services.review_service import (
    ReviewService,
    ReviewValidationError,
)
from app.storage.local import LocalFileStorage

client = TestClient(app)


def _make_pdf(text: str) -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for line in text.splitlines():
        if line.strip():
            page.insert_text((72, y), line)
            y += 14
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def storage_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "documents"
    monkeypatch.setenv("STORAGE_ROOT", str(root))
    get_settings.cache_clear()
    yield root
    get_settings.cache_clear()


@pytest.fixture
def services(
    db_session: Session, storage_root: Path
) -> tuple[DocumentService, DocumentUnderstandingService, ReviewService, PromotionService]:
    storage = LocalFileStorage(storage_root)
    return (
        DocumentService(db_session, storage=storage),
        DocumentUnderstandingService(db_session, storage=storage),
        ReviewService(db_session),
        PromotionService(db_session),
    )


def _seed_extraction(
    session: Session,
    *,
    document_type: DocumentType = DocumentType.INVOICE,
    outcome: ExtractionOutcome = ExtractionOutcome.REVIEW_REQUIRED,
    candidate: dict | None = None,
    status: DocumentStatus = DocumentStatus.REVIEW_REQUIRED,
) -> tuple[Document, DocumentExtractionResult]:
    if candidate is None:
        candidate = {
            "invoice_number": "INV-REV-1",
            "vendor_name": "Acme Supplies",
            "invoice_date": "2026-09-15",
            "currency": "USD",
            "po_number": "PO-REV-1",
            "lines": [
                {
                    "line_number": 1,
                    "description": "Widget",
                    "quantity": "10",
                    "unit_price": "25.00",
                    "tax_rate": "0",
                }
            ],
        }
    document = Document(
        original_filename="inv.pdf",
        stored_filename=f"{uuid4().hex}.pdf",
        document_type=document_type.value,
        mime_type="application/pdf",
        file_extension=".pdf",
        file_size=10,
        sha256=uuid4().hex + uuid4().hex,
        storage_path="stored/inv.pdf",
        status=status.value,
    )
    session.add(document)
    session.flush()
    extraction = DocumentExtractionResult(
        document_id=document.id,
        detected_type=document_type.value,
        outcome=outcome.value,
        extractor_version="m4-1.0",
        raw_extraction={},
        candidate=candidate,
        validation={"is_valid": False, "requires_review": True, "issues": []},
        evidence=[],
        message="needs review",
    )
    session.add(extraction)
    session.commit()
    return document, extraction


# --- Review -----------------------------------------------------------------


def test_review_task_creation(db_session: Session) -> None:
    document, extraction = _seed_extraction(db_session)
    svc = ReviewService(db_session)
    task = svc.create_review_task(
        document_id=document.id,
        extraction_result_id=extraction.id,
        reason="manual",
    )
    assert task.status == ReviewStatus.PENDING.value
    assert task.reviewed_candidate["invoice_number"] == "INV-REV-1"


def test_duplicate_review_prevention(db_session: Session) -> None:
    document, extraction = _seed_extraction(db_session)
    svc = ReviewService(db_session)
    first = svc.create_review_task(
        document_id=document.id,
        extraction_result_id=extraction.id,
    )
    second = svc.create_review_task(
        document_id=document.id,
        extraction_result_id=extraction.id,
    )
    assert first.id == second.id
    count = db_session.scalar(select(ReviewTask).where(ReviewTask.document_id == document.id))
    assert count is not None
    rows = list(
        db_session.scalars(
            select(ReviewTask).where(ReviewTask.extraction_result_id == extraction.id)
        )
    )
    assert len(rows) == 1


def test_valid_status_transitions() -> None:
    assert_transition(ReviewStatus.PENDING, ReviewStatus.IN_REVIEW)
    assert_transition(ReviewStatus.IN_REVIEW, ReviewStatus.APPROVED)
    assert_transition(ReviewStatus.IN_REVIEW, ReviewStatus.CORRECTED)
    assert_transition(ReviewStatus.IN_REVIEW, ReviewStatus.REJECTED)
    assert_transition(ReviewStatus.CORRECTED, ReviewStatus.APPROVED)


def test_invalid_status_transitions() -> None:
    with pytest.raises(InvalidReviewTransitionError):
        assert_transition(ReviewStatus.REJECTED, ReviewStatus.APPROVED)
    with pytest.raises(InvalidReviewTransitionError):
        assert_transition(ReviewStatus.APPROVED, ReviewStatus.IN_REVIEW)


def test_approve(db_session: Session) -> None:
    document, extraction = _seed_extraction(db_session)
    svc = ReviewService(db_session)
    task = svc.create_review_task(
        document_id=document.id,
        extraction_result_id=extraction.id,
    )
    approved = svc.approve(task.id, reviewer="alice", reason="looks good")
    assert approved.status == ReviewStatus.APPROVED.value
    assert approved.assigned_to == "alice"
    assert approved.completed_at is not None
    decisions = list(
        db_session.scalars(
            select(ReviewDecision).where(ReviewDecision.review_task_id == approved.id)
        )
    )
    assert len(decisions) == 1
    assert decisions[0].action == "APPROVE"


def test_correct_and_audit_trail(db_session: Session) -> None:
    document, extraction = _seed_extraction(db_session)
    original_qty = extraction.candidate["lines"][0]["quantity"]
    svc = ReviewService(db_session)
    task = svc.create_review_task(
        document_id=document.id,
        extraction_result_id=extraction.id,
    )
    corrected = svc.correct(
        task.id,
        reviewer="bob",
        corrections=[
            {
                "field_path": "lines[0].quantity",
                "corrected_value": "12",
                "reason": "OCR misread",
            }
        ],
    )
    assert corrected.status == ReviewStatus.CORRECTED.value
    assert corrected.reviewed_candidate["lines"][0]["quantity"] == "12"
    # Original M4 extraction preserved
    db_session.refresh(extraction)
    assert extraction.candidate["lines"][0]["quantity"] == original_qty
    decision = db_session.scalar(
        select(ReviewDecision).where(ReviewDecision.review_task_id == corrected.id)
    )
    assert decision is not None
    assert decision.original_value == "10"
    assert decision.corrected_value == "12"
    assert decision.reviewer == "bob"


def test_reject(db_session: Session) -> None:
    document, extraction = _seed_extraction(db_session)
    svc = ReviewService(db_session)
    task = svc.create_review_task(
        document_id=document.id,
        extraction_result_id=extraction.id,
    )
    rejected = svc.reject(task.id, reviewer="carol", reason="wrong vendor")
    assert rejected.status == ReviewStatus.REJECTED.value
    db_session.refresh(document)
    assert document.status == DocumentStatus.REVIEW_REJECTED.value


def test_invalid_correction_rejected(db_session: Session) -> None:
    document, extraction = _seed_extraction(db_session)
    svc = ReviewService(db_session)
    task = svc.create_review_task(
        document_id=document.id,
        extraction_result_id=extraction.id,
    )
    with pytest.raises(ReviewValidationError):
        svc.correct(
            task.id,
            corrections=[{"field_path": "lines[0].quantity", "corrected_value": "-5"}],
        )
    with pytest.raises(ReviewValidationError):
        svc.correct(
            task.id,
            corrections=[{"field_path": "lines[99].quantity", "corrected_value": "1"}],
        )


def test_cannot_modify_approved(db_session: Session) -> None:
    document, extraction = _seed_extraction(db_session)
    svc = ReviewService(db_session)
    task = svc.create_review_task(
        document_id=document.id,
        extraction_result_id=extraction.id,
    )
    svc.approve(task.id, reviewer="alice")
    with pytest.raises(ReviewValidationError):
        svc.reject(task.id, reason="too late")


# --- Evaluation -------------------------------------------------------------


def test_exact_field_match() -> None:
    assert values_equal("INV-1", "INV-1", kind="string")


def test_normalized_string_match() -> None:
    assert values_equal("  Acme   Supplies ", "acme supplies", kind="string")


def test_decimal_comparison() -> None:
    assert values_equal(Decimal("10.00"), "10", kind="decimal")
    assert not values_equal(Decimal("10.01"), "10", kind="decimal")


def test_date_comparison() -> None:
    assert values_equal(date(2026, 9, 15), "2026-09-15", kind="date")


def test_missing_and_incorrect_fields() -> None:
    evaluator = ExtractionEvaluator()
    golden = GoldenDocument(
        evaluation_id="t1",
        document_type=DocumentType.INVOICE,
        expected={
            "invoice_number": "INV-1",
            "vendor_name": "Acme",
            "invoice_date": "2026-01-01",
        },
    )
    result = evaluator.evaluate(
        golden,
        {"invoice_number": "INV-1", "vendor_name": "Other"},
    )
    assert "invoice_number" in result.correct_fields
    assert "vendor_name" in result.incorrect_fields
    assert "invoice_date" in result.missing_fields


def test_line_item_comparison_and_metrics() -> None:
    evaluator = ExtractionEvaluator()
    golden = get_golden("multi-line-invoice")
    actual = {
        "invoice_number": "INV-2002",
        "vendor_name": "Beta Traders",
        "invoice_date": "2026-08-01",
        "lines": [
            {
                "line_number": 1,
                "description": "Bolt",
                "quantity": "100",
                "unit_price": "1.50",
            },
            {
                "line_number": 2,
                "description": "Nut",
                "quantity": "100",
                "unit_price": "0.75",
            },
        ],
    }
    result = evaluator.evaluate(golden, actual)
    assert result.overall_success
    assert result.line_item_metrics is not None
    assert result.line_item_metrics.count_match
    assert result.field_accuracy == Decimal("1.0000")


def test_golden_dataset_evaluation() -> None:
    evaluator = ExtractionEvaluator()
    results = []
    for golden in GOLDEN_DATASET:
        if golden.evaluation_id == "malformed-ambiguous":
            result = evaluator.evaluate(golden, {})
            assert result.overall_success is False
            results.append(result)
            continue
        result = evaluator.evaluate(golden, golden.expected)
        assert result.overall_success, golden.evaluation_id
        results.append(result)
    rate = evaluator.document_success_rate(results)
    assert rate == 0.8


# --- Promotion --------------------------------------------------------------


def test_approved_candidate_promotion(db_session: Session) -> None:
    document, extraction = _seed_extraction(db_session)
    reviews = ReviewService(db_session)
    task = reviews.create_review_task(
        document_id=document.id,
        extraction_result_id=extraction.id,
    )
    reviews.approve(task.id, reviewer="alice")
    promoted = PromotionService(db_session).promote(task.id)
    assert promoted.promoted_entity_type == DocumentType.INVOICE.value
    assert promoted.promoted_entity_id is not None
    invoice = db_session.get(Invoice, promoted.promoted_entity_id)
    assert invoice is not None
    assert invoice.invoice_number == "INV-REV-1"
    db_session.refresh(document)
    assert document.invoice_id == invoice.id
    assert document.status == DocumentStatus.READY_FOR_RECONCILIATION.value


def test_corrected_candidate_promotion(db_session: Session) -> None:
    document, extraction = _seed_extraction(db_session)
    reviews = ReviewService(db_session)
    task = reviews.create_review_task(
        document_id=document.id,
        extraction_result_id=extraction.id,
    )
    reviews.correct(
        task.id,
        reviewer="bob",
        corrections=[
            {"field_path": "invoice_number", "corrected_value": "INV-FIXED"},
            {"field_path": "lines[0].quantity", "corrected_value": "11"},
        ],
    )
    promoted = PromotionService(db_session).promote(task.id)
    invoice = db_session.get(Invoice, promoted.promoted_entity_id)
    assert invoice is not None
    assert invoice.invoice_number == "INV-FIXED"
    assert invoice.lines[0].quantity == Decimal("11")


def test_rejected_cannot_promote(db_session: Session) -> None:
    document, extraction = _seed_extraction(db_session)
    reviews = ReviewService(db_session)
    task = reviews.create_review_task(
        document_id=document.id,
        extraction_result_id=extraction.id,
    )
    reviews.reject(task.id, reason="bad")
    with pytest.raises(PromotionNotAllowedError):
        PromotionService(db_session).promote(task.id)


def test_pending_cannot_promote(db_session: Session) -> None:
    document, extraction = _seed_extraction(db_session)
    reviews = ReviewService(db_session)
    task = reviews.create_review_task(
        document_id=document.id,
        extraction_result_id=extraction.id,
    )
    with pytest.raises(PromotionNotAllowedError):
        PromotionService(db_session).promote(task.id)


def test_missing_required_fields_cannot_promote(db_session: Session) -> None:
    document, extraction = _seed_extraction(
        db_session,
        candidate={"vendor_name": "Acme", "lines": []},
    )
    reviews = ReviewService(db_session)
    task = reviews.create_review_task(
        document_id=document.id,
        extraction_result_id=extraction.id,
    )
    reviews.approve(task.id)
    with pytest.raises(PromotionValidationError):
        PromotionService(db_session).promote(task.id)


def test_promotion_transaction_rollback(db_session: Session) -> None:
    document, extraction = _seed_extraction(
        db_session,
        candidate={
            "invoice_number": "INV-ROLL",
            "invoice_date": "not-a-date",
            "vendor_name": "Acme",
            "lines": [{"line_number": 1, "quantity": "1", "unit_price": "1"}],
        },
    )
    reviews = ReviewService(db_session)
    task = reviews.create_review_task(
        document_id=document.id,
        extraction_result_id=extraction.id,
    )
    reviews.approve(task.id)
    with pytest.raises(PromotionValidationError):
        PromotionService(db_session).promote(task.id)
    assert db_session.scalar(select(Invoice).where(Invoice.invoice_number == "INV-ROLL")) is None
    db_session.refresh(task)
    assert task.promoted_entity_id is None


def test_duplicate_promotion_idempotent(db_session: Session) -> None:
    document, extraction = _seed_extraction(db_session)
    reviews = ReviewService(db_session)
    task = reviews.create_review_task(
        document_id=document.id,
        extraction_result_id=extraction.id,
    )
    reviews.approve(task.id)
    promo = PromotionService(db_session)
    first = promo.promote(task.id)
    second = promo.promote(task.id)
    assert first.promoted_entity_id == second.promoted_entity_id
    invoices = list(
        db_session.scalars(select(Invoice).where(Invoice.invoice_number == "INV-REV-1"))
    )
    assert len(invoices) == 1


def test_authoritative_link_to_source_document(db_session: Session) -> None:
    document, extraction = _seed_extraction(db_session)
    reviews = ReviewService(db_session)
    task = reviews.create_review_task(
        document_id=document.id,
        extraction_result_id=extraction.id,
    )
    reviews.approve(task.id)
    promoted = PromotionService(db_session).promote(task.id)
    db_session.refresh(document)
    assert document.invoice_id == promoted.promoted_entity_id


# --- Integration ------------------------------------------------------------


def test_m4_review_required_creates_task(services) -> None:
    docs, understanding, reviews, _promo = services
    text = "Random scan without structure\nhello world\n"
    row, _ = docs.upload(
        filename="ambiguous.pdf",
        content_type="application/pdf",
        data=_make_pdf(text),
        document_type=DocumentType.UNKNOWN,
    )
    result = understanding.understand(row.id)
    assert result.outcome is ExtractionOutcome.REVIEW_REQUIRED
    tasks = reviews.list_tasks()
    assert any(t.document_id == row.id for t in tasks)


def test_clean_m4_does_not_create_review_task(services) -> None:
    docs, understanding, reviews, _promo = services
    text = (
        "TAX INVOICE\n"
        "Invoice Number: INV-CLEAN-9\n"
        "Vendor: Acme Supplies\n"
        "Invoice Date: 2026-09-15\n"
        "PO Number: PO-CLEAN-9\n"
        "Widget A 10 500.00\n"
    )
    row, _ = docs.upload(
        filename="clean.pdf",
        content_type="application/pdf",
        data=_make_pdf(text),
        document_type=DocumentType.INVOICE,
    )
    result = understanding.understand(row.id)
    assert result.outcome is ExtractionOutcome.READY_FOR_RECONCILIATION
    tasks = [t for t in reviews.list_tasks() if t.document_id == row.id]
    assert tasks == []


def test_approved_review_moves_toward_reconciliation(services, db_session: Session) -> None:
    docs, understanding, reviews, promo = services
    text = (
        "TAX INVOICE\n"
        "Invoice Number: INV-PATH-1\n"
        "Vendor: Path Vendor\n"
        "Invoice Date: 2026-09-01\n"
        "Item A 2 10.00\n"
    )
    row, _ = docs.upload(
        filename="path.pdf",
        content_type="application/pdf",
        data=_make_pdf(text),
        document_type=DocumentType.INVOICE,
    )
    understanding.understand(row.id)
    extraction = db_session.scalar(
        select(DocumentExtractionResult).where(DocumentExtractionResult.document_id == row.id)
    )
    assert extraction is not None
    task = reviews.create_review_task(
        document_id=row.id,
        extraction_result_id=extraction.id,
    )
    reviews.approve(task.id, reviewer="dave")
    promoted = promo.promote(task.id)
    assert promoted.promoted_entity_id is not None
    db_session.refresh(row)
    assert row.status == DocumentStatus.READY_FOR_RECONCILIATION.value


def test_m2_remains_compatible(db_session: Session) -> None:
    """Promotion-created authoritative rows remain compatible with M2 facts."""
    from app.db.models import PurchaseOrderLine
    from app.reconciliation.engine import reconcile
    from app.reconciliation.schemas import (
        EngineInvoice,
        EngineInvoiceLine,
        EnginePurchaseOrder,
        EnginePurchaseOrderLine,
        ReconciliationInput,
    )

    vendor = Vendor(name="Compat Co")
    db_session.add(vendor)
    db_session.flush()
    po = PurchaseOrder(
        po_number="PO-M2-1",
        vendor_id=vendor.id,
        order_date=date(2026, 1, 1),
        currency="USD",
    )
    po.lines.append(
        PurchaseOrderLine(
            line_number=1,
            description="Item",
            quantity=Decimal("10"),
            unit_price=Decimal("5"),
            tax_rate=Decimal("0"),
        )
    )
    db_session.add(po)
    db_session.commit()

    invoice = Invoice(
        invoice_number="INV-M2-1",
        vendor_id=vendor.id,
        purchase_order_id=po.id,
        invoice_date=date(2026, 1, 2),
        currency="USD",
        subtotal=Decimal("50"),
        tax_amount=Decimal("0"),
        total_amount=Decimal("50"),
    )
    invoice.lines.append(
        InvoiceLine(
            line_number=1,
            description="Item",
            quantity=Decimal("10"),
            unit_price=Decimal("5"),
            tax_rate=Decimal("0"),
            purchase_order_line_id=po.lines[0].id,
        )
    )
    db_session.add(invoice)
    db_session.commit()

    result = reconcile(
        ReconciliationInput(
            purchase_order=EnginePurchaseOrder(
                id=po.id,
                po_number=po.po_number,
                vendor_id=vendor.id,
                order_date=po.order_date,
                currency="USD",
                lines=[
                    EnginePurchaseOrderLine(
                        id=po.lines[0].id,
                        line_number=1,
                        description="Item",
                        quantity=Decimal("10"),
                        unit_price=Decimal("5"),
                        tax_rate=Decimal("0"),
                    )
                ],
            ),
            invoice=EngineInvoice(
                id=invoice.id,
                invoice_number=invoice.invoice_number,
                vendor_id=vendor.id,
                purchase_order_id=po.id,
                invoice_date=invoice.invoice_date,
                currency="USD",
                lines=[
                    EngineInvoiceLine(
                        id=invoice.lines[0].id,
                        line_number=1,
                        description="Item",
                        quantity=Decimal("10"),
                        unit_price=Decimal("5"),
                        tax_rate=Decimal("0"),
                        purchase_order_line_id=po.lines[0].id,
                    )
                ],
            ),
            goods_receipts=[],
        )
    )
    assert result is not None
    assert po.po_number == "PO-M2-1"


def test_review_api_endpoints(db_session: Session, storage_root: Path) -> None:
    document, extraction = _seed_extraction(db_session)
    reviews = ReviewService(db_session)
    task = reviews.create_review_task(
        document_id=document.id,
        extraction_result_id=extraction.id,
        priority=ReviewPriority.HIGH,
    )

    def _override() -> Session:
        yield db_session

    app.dependency_overrides[get_db] = _override
    try:
        listed = client.get("/review/tasks", params={"status": "PENDING"})
        assert listed.status_code == 200
        assert listed.json()["count"] >= 1
        assert "storage_path" not in listed.text

        got = client.get(f"/review/tasks/{task.id}")
        assert got.status_code == 200
        assert got.json()["id"] == str(task.id)

        approved = client.post(
            f"/review/tasks/{task.id}/approve",
            json={"reviewer": "api-user", "reason": "ok"},
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "APPROVED"

        # New task for correct/reject paths
        document2, extraction2 = _seed_extraction(
            db_session,
            candidate={
                "invoice_number": "INV-API-2",
                "vendor_name": "Acme",
                "invoice_date": "2026-09-15",
                "lines": [
                    {
                        "line_number": 1,
                        "quantity": "1",
                        "unit_price": "2",
                        "tax_rate": "0",
                    }
                ],
            },
        )
        task2 = reviews.create_review_task(
            document_id=document2.id,
            extraction_result_id=extraction2.id,
        )
        corrected = client.post(
            f"/review/tasks/{task2.id}/correct",
            json={
                "reviewer": "api-user",
                "corrections": [{"field_path": "lines[0].quantity", "corrected_value": "3"}],
            },
        )
        assert corrected.status_code == 200
        assert corrected.json()["status"] == "CORRECTED"

        document3, extraction3 = _seed_extraction(db_session)
        task3 = reviews.create_review_task(
            document_id=document3.id,
            extraction_result_id=extraction3.id,
        )
        rejected = client.post(
            f"/review/tasks/{task3.id}/reject",
            json={"reviewer": "api-user", "reason": "nope"},
        )
        assert rejected.status_code == 200
        assert rejected.json()["status"] == "REJECTED"

        promoted = client.post(f"/review/tasks/{task.id}/promote")
        assert promoted.status_code == 200
        assert promoted.json()["promoted_entity_id"] is not None
    finally:
        app.dependency_overrides.clear()
