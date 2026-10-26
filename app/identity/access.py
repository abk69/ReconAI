"""Map an HTTP request to the permission it requires."""

from __future__ import annotations

from fastapi import Request

from app.identity.permissions import Permission

_SAFE = frozenset({"GET", "HEAD", "OPTIONS"})


def permission_for(request: Request) -> Permission:
    method = request.method.upper()
    path = request.url.path.rstrip("/") or "/"
    if method in _SAFE:
        return Permission.VIEW
    if path.endswith("/execute"):
        return Permission.EXECUTE
    if path.endswith("/promote"):
        return Permission.PROMOTE
    if path.endswith("/approve") or path.endswith("/correct") or path.endswith("/reject"):
        if "/resolution-plans/" in path:
            return Permission.APPROVE
        return Permission.REVIEW
    if path.endswith("/policy-explanation") or path.endswith("/resolution-plan"):
        return Permission.PLAN
    if path.endswith("/understand") or path.endswith("/llm-understand"):
        return Permission.UNDERSTAND
    if path.endswith("/jobs") and method == "POST":
        return Permission.UNDERSTAND
    if "/jobs/" in path and path.endswith("/retry"):
        return Permission.UNDERSTAND
    if "/jobs/" in path and path.endswith("/cancel"):
        return Permission.UNDERSTAND
    if path.endswith("/review/tasks"):
        return Permission.REQUEST_REVIEW
    if path.endswith("/reconciliation/run"):
        return Permission.RECONCILE
    if "/policies" in path:
        return Permission.POLICY
    if path.endswith("/documents") and method == "POST":
        return Permission.UPLOAD
    if path.endswith("/users"):
        return Permission.MANAGE_USERS
    return Permission.OPERATE
