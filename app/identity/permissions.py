"""Role permissions. The client never supplies a role that is trusted."""

from __future__ import annotations

from enum import StrEnum

from app.domain.enums import MembershipRole


class Permission(StrEnum):
    VIEW = "view"
    UPLOAD = "upload"
    UNDERSTAND = "understand"
    REQUEST_REVIEW = "request_review"
    OPERATE = "operate"
    REVIEW = "review"
    PROMOTE = "promote"
    RECONCILE = "reconcile"
    PLAN = "plan"
    APPROVE = "approve"
    EXECUTE = "execute"
    POLICY = "policy"
    MANAGE_USERS = "manage_users"


_VIEWER = {Permission.VIEW}
_OPERATOR = _VIEWER | {
    Permission.UPLOAD,
    Permission.UNDERSTAND,
    Permission.REQUEST_REVIEW,
    Permission.OPERATE,
}
_REVIEWER = _OPERATOR | {Permission.REVIEW, Permission.PROMOTE, Permission.RECONCILE}
_APPROVER = _VIEWER | {Permission.PLAN, Permission.APPROVE}
_ADMIN = set(Permission)

ROLE_PERMISSIONS: dict[MembershipRole, set[Permission]] = {
    MembershipRole.VIEWER: _VIEWER,
    MembershipRole.OPERATOR: _OPERATOR,
    MembershipRole.REVIEWER: _REVIEWER,
    MembershipRole.APPROVER: _APPROVER,
    MembershipRole.ADMIN: _ADMIN,
}


def allows(role: str, permission: Permission) -> bool:
    try:
        parsed = MembershipRole(role)
    except ValueError:
        return False
    return permission in ROLE_PERMISSIONS[parsed]
