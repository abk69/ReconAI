"""Reconciliation API routes (thin adapters)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.models import ReconciliationException
from app.db.session import get_db
from app.llm.base import LLMProviderError
from app.llm.grounding_schemas import PolicyExplanationRequest, PolicyExplanationResponse
from app.schemas.reconciliation import (
    ExceptionResponse,
    ReconciliationRunRequest,
    ReconciliationRunResponse,
    ReconciliationSummaryResponse,
)
from app.services.policy_grounding_service import (
    PolicyGroundingNotFoundError,
    PolicyGroundingService,
    PolicyGroundingValidationError,
)
from app.services.reconciliation_service import (
    ReconciliationNotFoundError,
    ReconciliationService,
    ReconciliationServiceError,
)

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])

DbSession = Annotated[Session, Depends(get_db)]


@router.post(
    "/run",
    response_model=ReconciliationRunResponse,
    status_code=status.HTTP_200_OK,
)
def run_reconciliation(
    body: ReconciliationRunRequest,
    session: DbSession,
) -> ReconciliationRunResponse:
    """Run deterministic PO/GRN/Invoice reconciliation for the given documents."""
    if body.purchase_order_id is None and body.invoice_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="At least one of purchase_order_id or invoice_id is required.",
        )

    service = ReconciliationService(session)
    try:
        result = service.run(
            purchase_order_id=body.purchase_order_id,
            invoice_id=body.invoice_id,
            quantity_tolerance=body.quantity_tolerance,
            price_tolerance_percent=body.price_tolerance_percent,
            tax_rate_tolerance_percent=body.tax_rate_tolerance_percent,
            persist=body.persist,
        )
    except ReconciliationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ReconciliationServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return ReconciliationRunResponse(
        status=result.status,
        exception_count=result.exception_count,
        exceptions=[
            ExceptionResponse(
                exception_type=exc.exception_type,
                severity=exc.severity,
                message=exc.message,
                fingerprint=exc.fingerprint,
                purchase_order_id=exc.purchase_order_id,
                goods_receipt_id=exc.goods_receipt_id,
                invoice_id=exc.invoice_id,
                source_document_ids=exc.source_document_ids,
                evidence=exc.evidence,
            )
            for exc in result.exceptions
        ],
        summary=ReconciliationSummaryResponse(
            exception_count_by_type=result.summary.exception_count_by_type,
            po_line_count=result.summary.po_line_count,
            grn_count=result.summary.grn_count,
            invoice_line_count=result.summary.invoice_line_count,
            total_ordered_quantity=result.summary.total_ordered_quantity,
            total_received_quantity=result.summary.total_received_quantity,
            total_invoiced_quantity=result.summary.total_invoiced_quantity,
        ),
        document_ids=result.document_ids,
        purchase_order_id=result.purchase_order_id,
        invoice_id=result.invoice_id,
        goods_receipt_ids=result.goods_receipt_ids,
    )


@router.post(
    "/exceptions/{exception_id}/policy-explanation",
    response_model=PolicyExplanationResponse,
)
def explain_exception_policy(
    exception_id: UUID,
    session: DbSession,
    body: Annotated[PolicyExplanationRequest | None, Body()] = None,
) -> PolicyExplanationResponse:
    """Grounded policy explanation for an M2 exception (AI-derived; does not mutate M2)."""
    req = body or PolicyExplanationRequest()
    try:
        result = PolicyGroundingService(session).explain_exception(
            exception_id,
            policy_version_id=req.policy_version_id,
            policy_document_id=req.policy_document_id,
            top_k=req.top_k,
            persist=req.persist,
        )
    except PolicyGroundingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PolicyGroundingValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except LLMProviderError as exc:
        # Provider errors are usually returned as structured PROVIDER_ERROR by the
        # service; this catches unexpected raises before that mapping.
        code = status.HTTP_502_BAD_GATEWAY
        if exc.code == "MISSING_API_KEY":
            code = status.HTTP_503_SERVICE_UNAVAILABLE
        raise HTTPException(status_code=code, detail=str(exc)) from exc

    exc_row = session.get(ReconciliationException, exception_id)
    return PolicyExplanationResponse(
        **result.model_dump(),
        exception_type=exc_row.exception_type if exc_row else None,
        exception_status=exc_row.status if exc_row else None,
        reconciliation_evidence=dict(exc_row.evidence or {}) if exc_row else {},
    )
