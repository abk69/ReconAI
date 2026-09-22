"""M9 hardening check: Postgres connectivity + migration + E2E risk flow."""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import create_engine, func, inspect, select, text

from app.core.config import get_settings


def check_postgres(*, after_migrate: bool = False) -> None:
    url = get_settings().database_url
    print(f"DATABASE_URL dialect: {url.split('://', 1)[0]}")
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    with engine.connect() as conn:
        ver = conn.execute(text("select version()")).scalar()
        print(f"Postgres OK: {ver}")
        ext = conn.execute(
            text("select extname from pg_extension where extname = 'vector'")
        ).scalar()
        print(f"pgvector extension: {ext!r}")
        if after_migrate and ext != "vector":
            raise RuntimeError("pgvector extension missing after migrations")
    engine.dispose()


def upgrade_alembic() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    print("Running alembic upgrade head ...")
    command.upgrade(cfg, "head")
    engine = create_engine(get_settings().database_url)
    with engine.connect() as conn:
        rev = conn.execute(text("select version_num from alembic_version")).scalar()
        print(f"alembic_version: {rev}")
        cols = [
            c["name"]
            for c in inspect(conn).get_columns("risk_profiles")
        ]
        print(f"risk_profiles columns ({len(cols)}): {', '.join(cols)}")
        uniques = inspect(conn).get_unique_constraints("risk_profiles")
        print(f"unique constraints: {[u['name'] for u in uniques]}")
    engine.dispose()


def e2e_risk_flow() -> None:
    from fastapi.testclient import TestClient

    from app.anomaly.enums import AnomalyType
    from app.core.config import get_settings
    from app.db.models import (
        Invoice,
        InvoiceLine,
        PurchaseOrder,
        PurchaseOrderLine,
        RiskProfileRecord,
        Vendor,
    )
    from app.db.session import get_db, get_engine, get_session_factory
    from app.domain.enums import InvoiceStatus, PurchaseOrderStatus
    from app.main import app
    from app.services.anomaly_service import AnomalyService
    from app.services.risk_service import RiskService

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    factory = get_session_factory()
    session = factory()

    try:
        vendor = Vendor(name=f"Hardening-{uuid4().hex[:6]}", tax_id=f"T-{uuid4().hex[:8]}")
        session.add(vendor)
        session.flush()
        po = PurchaseOrder(
            po_number=f"PO-H-{uuid4().hex[:8]}",
            vendor_id=vendor.id,
            order_date=date(2026, 1, 1),
            currency="USD",
            status=PurchaseOrderStatus.OPEN.value,
        )
        session.add(po)
        session.flush()
        po_line = PurchaseOrderLine(
            purchase_order_id=po.id,
            line_number=1,
            description="Widget",
            quantity=Decimal("10"),
            unit_price=Decimal("100"),
            tax_rate=Decimal("0"),
        )
        session.add(po_line)
        session.flush()
        inv = Invoice(
            invoice_number=f"INV-H-{uuid4().hex[:8]}",
            vendor_id=vendor.id,
            purchase_order_id=po.id,
            invoice_date=date(2026, 1, 15),
            currency="USD",
            status=InvoiceStatus.RECEIVED.value,
            subtotal=Decimal("1500"),
            tax_amount=Decimal("0"),
            total_amount=Decimal("1500"),
        )
        session.add(inv)
        session.flush()
        session.add(
            InvoiceLine(
                invoice_id=inv.id,
                purchase_order_line_id=po_line.id,
                line_number=1,
                description="Widget",
                quantity=Decimal("10"),
                unit_price=Decimal("150"),  # 50% price variance → anomaly
                tax_rate=Decimal("0"),
            )
        )
        session.commit()
        invoice_id = inv.id
        print(f"Seeded invoice={invoice_id}")

        # M9.1 detect
        signals = AnomalyService(session).detect_for_invoice(invoice_id)
        print(f"Anomaly signals: {len(signals)} types={[s.anomaly_type for s in signals]}")
        assert any(s.anomaly_type == AnomalyType.PRICE_VARIANCE.value for s in signals)

        as_of = date.today()
        past = date(2020, 1, 1)
        risk = RiskService(session)
        p1 = risk.calculate_invoice_risk(invoice_id, as_of=as_of)
        print(
            f"Risk profile1 id={p1.id} score={p1.score} band={p1.risk_band} "
            f"fp={p1.fingerprint[:16]}... signals={p1.signal_count}"
        )
        assert p1.score > 0
        assert p1.signal_count >= 1

        # Fingerprint reuse
        p2 = risk.calculate_invoice_risk(invoice_id, as_of=as_of)
        assert p1.id == p2.id
        count = session.scalar(
            select(func.count())
            .select_from(RiskProfileRecord)
            .where(
                RiskProfileRecord.entity_id == invoice_id,
                RiskProfileRecord.as_of == as_of,
            )
        )
        assert count == 1
        print("Fingerprint reuse: OK (same row)")

        # Past as_of excludes signals detected later (point-in-time)
        p_past = risk.calculate_invoice_risk(invoice_id, as_of=past)
        assert p_past.id != p1.id
        assert p_past.signal_count == 0
        assert p_past.score == 0
        print(f"as_of past ({past}) -> score=0 signal_count=0: OK")

        # Different as_of => new row (fingerprint includes as_of).
        other = as_of + __import__("datetime").timedelta(days=1)
        p3 = risk.calculate_invoice_risk(invoice_id, as_of=other)
        assert p3.id != p1.id
        session.refresh(p1)
        assert p1.score == p2.score  # historical immutable
        print(f"as_of other profile id={p3.id} score={p3.score}; historical unchanged: OK")

        # Deterministic recalculation
        p1_again = risk.calculate_invoice_risk(invoice_id, as_of=as_of)
        assert p1_again.score == p1.score
        assert p1_again.fingerprint == p1.fingerprint
        print("as_of determinism: OK")

        # API
        def _override():
            yield session

        app.dependency_overrides[get_db] = _override
        try:
            client = TestClient(app)
            resp = client.get(
                f"/risk/invoices/{invoice_id}",
                params={"as_of": as_of.isoformat()},
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["score"] == p1.score
            assert body["fingerprint"] == p1.fingerprint
            assert "not a probability of fraud" in body["note"].casefold()
            print(f"GET /risk/invoices/{{id}} -> {resp.status_code} score={body['score']} OK")
        finally:
            app.dependency_overrides.clear()

        # No financial mutation
        session.refresh(inv)
        assert inv.total_amount == Decimal("1500")
        assert inv.lines[0].unit_price == Decimal("150")
        print("No financial mutation: OK")

        print("E2E HARDENING PASSED")
    finally:
        session.close()


def main() -> int:
    try:
        check_postgres(after_migrate=False)
        upgrade_alembic()
        check_postgres(after_migrate=True)
        e2e_risk_flow()
    except Exception as exc:
        print(f"HARDENING FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
