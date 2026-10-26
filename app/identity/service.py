"""Sessions, login, and user provisioning. Tenant id is never taken from the client."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import LoginAttempt, Membership, Tenant, User, UserSession
from app.db.tenant_filter import suspend_tenant_filter
from app.domain.enums import MembershipRole
from app.identity.passwords import hash_email, hash_password, verify_password
from app.identity.permissions import Permission, allows

SESSION_COOKIE = "reconai_session"
CSRF_COOKIE = "reconai_csrf"
_SESSION_HOURS = 12
_LOCK_WINDOW = timedelta(minutes=15)
_LOCK_LIMIT = 8
_WEAK = frozenset({"password", "reconai", "admin", "changeme", "password1234"})


class AuthError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: str
    email: str
    csrf_token: str

    def allows(self, permission: Permission) -> bool:
        return allows(self.role, permission)


def validate_password_choice(password: str) -> None:
    if len(password) < 12 or password.strip().casefold() in _WEAK:
        raise AuthError("weak_password", "Choose a password of at least 12 characters.")


class AuthService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def login(self, email: str, password: str) -> tuple[Principal, str]:
        email_key = hash_email(email)
        if self._locked(email_key):
            raise AuthError("rate_limited", "Too many sign-in attempts. Try again later.")
        with suspend_tenant_filter():
            user = self._session.scalar(select(User).where(User.email == email.strip().casefold()))
            membership = None
            if user is not None and user.is_active:
                membership = self._session.scalar(
                    select(Membership)
                    .where(Membership.user_id == user.id)
                    .order_by(Membership.created_at)
                )
            if (
                user is None
                or membership is None
                or not verify_password(password, user.password_hash)
            ):
                self._session.add(LoginAttempt(email_hash=email_key))
                self._session.commit()
                raise AuthError("invalid_login", "Email or password is incorrect.")
            raw, row = self._new_session(user_id=user.id, tenant_id=membership.tenant_id)
            principal = Principal(
                user_id=user.id,
                tenant_id=membership.tenant_id,
                role=membership.role,
                email=user.email,
                csrf_token=row.csrf_token,
            )
            self._session.commit()
            return principal, raw

    def principal_for_token(self, raw_token: str) -> Principal | None:
        digest = _token_hash(raw_token)
        now = datetime.now(UTC)
        with suspend_tenant_filter():
            row = self._session.scalar(select(UserSession).where(UserSession.token_hash == digest))
            if row is None or row.revoked_at is not None or _aware(row.expires_at) <= now:
                return None
            user = self._session.get(User, row.user_id)
            membership = self._session.scalar(
                select(Membership).where(
                    Membership.user_id == row.user_id,
                    Membership.tenant_id == row.tenant_id,
                )
            )
        if user is None or not user.is_active or membership is None:
            return None
        return Principal(
            user_id=user.id,
            tenant_id=row.tenant_id,
            role=membership.role,
            email=user.email,
            csrf_token=row.csrf_token,
        )

    def logout(self, raw_token: str) -> None:
        digest = _token_hash(raw_token)
        with suspend_tenant_filter():
            row = self._session.scalar(select(UserSession).where(UserSession.token_hash == digest))
            if row is not None and row.revoked_at is None:
                row.revoked_at = datetime.now(UTC)
                self._session.commit()

    def provision_user(
        self,
        *,
        email: str,
        password: str,
        role: MembershipRole,
        tenant_id: uuid.UUID,
    ) -> User:
        validate_password_choice(password)
        normalized = email.strip().casefold()
        with suspend_tenant_filter():
            existing = self._session.scalar(select(User).where(User.email == normalized))
        if existing is not None:
            raise AuthError("email_taken", "That email is already registered.")
        user = User(email=normalized, password_hash=hash_password(password), is_active=True)
        self._session.add(user)
        self._session.flush()
        self._session.add(Membership(user_id=user.id, tenant_id=tenant_id, role=role.value))
        self._session.commit()
        return user

    def bootstrap(self, *, email: str, password: str, tenant_name: str) -> tuple[Tenant, User]:
        with suspend_tenant_filter():
            existing = self._session.scalar(select(func.count()).select_from(User))
        if existing:
            raise AuthError("already_bootstrapped", "A user already exists. Bootstrap is closed.")
        validate_password_choice(password)
        tenant = Tenant(name=tenant_name.strip())
        self._session.add(tenant)
        self._session.flush()
        user = User(
            email=email.strip().casefold(),
            password_hash=hash_password(password),
            is_active=True,
        )
        self._session.add(user)
        self._session.flush()
        self._session.add(
            Membership(user_id=user.id, tenant_id=tenant.id, role=MembershipRole.ADMIN.value)
        )
        self._session.commit()
        return tenant, user

    def _locked(self, email_hash: str) -> bool:
        cutoff = datetime.now(UTC) - _LOCK_WINDOW
        count = self._session.scalar(
            select(func.count())
            .select_from(LoginAttempt)
            .where(LoginAttempt.email_hash == email_hash, LoginAttempt.created_at >= cutoff)
        )
        return bool(count and count >= _LOCK_LIMIT)

    def _new_session(self, *, user_id: uuid.UUID, tenant_id: uuid.UUID) -> tuple[str, UserSession]:
        raw = secrets.token_urlsafe(32)
        row = UserSession(
            user_id=user_id,
            tenant_id=tenant_id,
            token_hash=_token_hash(raw),
            csrf_token=secrets.token_urlsafe(32),
            expires_at=datetime.now(UTC) + timedelta(hours=_SESSION_HOURS),
        )
        self._session.add(row)
        self._session.flush()
        return raw, row


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
