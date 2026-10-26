"""Login, logout, current user, and admin provisioning."""

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.domain.enums import MembershipRole
from app.identity.permissions import Permission
from app.identity.service import CSRF_COOKIE, SESSION_COOKIE, AuthError, AuthService, Principal

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class UserCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=256)
    role: MembershipRole = MembershipRole.VIEWER


class PrincipalResponse(BaseModel):
    user_id: str
    tenant_id: str
    email: str
    role: str


def _principal_response(principal: Principal) -> PrincipalResponse:
    return PrincipalResponse(
        user_id=str(principal.user_id),
        tenant_id=str(principal.tenant_id),
        email=principal.email,
        role=principal.role,
    )


def _set_cookies(response: Response, raw_token: str, csrf_token: str) -> None:
    settings = get_settings()
    secure = settings.app_env != "local"
    response.set_cookie(
        SESSION_COOKIE,
        raw_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=12 * 60 * 60,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        httponly=False,
        secure=secure,
        samesite="lax",
        max_age=12 * 60 * 60,
        path="/",
    )


@router.post("/login", response_model=PrincipalResponse)
def login(body: LoginRequest, response: Response, session: DbSession) -> PrincipalResponse:
    try:
        principal, raw = AuthService(session).login(body.email, body.password)
    except AuthError as exc:
        code = (
            status.HTTP_429_TOO_MANY_REQUESTS
            if exc.code == "rate_limited"
            else status.HTTP_401_UNAUTHORIZED
        )
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    _set_cookies(response, raw, principal.csrf_token)
    return _principal_response(principal)


@router.post("/logout")
def logout(request: Request, response: Response, session: DbSession) -> dict[str, str]:
    raw = request.cookies.get(SESSION_COOKIE)
    if raw:
        principal = AuthService(session).principal_for_token(raw)
        header = request.headers.get("x-csrf-token", "")
        if principal is not None and (not header or header != principal.csrf_token):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This action failed the session check.",
            )
        AuthService(session).logout(raw)
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return {"status": "signed_out"}


@router.get("/me", response_model=PrincipalResponse)
def me(principal: CurrentUser) -> PrincipalResponse:
    return _principal_response(principal)


@router.post("/users", response_model=PrincipalResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreateRequest,
    principal: CurrentUser,
    session: DbSession,
) -> PrincipalResponse:
    if not principal.allows(Permission.MANAGE_USERS):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot do that.")
    try:
        user = AuthService(session).provision_user(
            email=body.email,
            password=body.password,
            role=body.role,
            tenant_id=principal.tenant_id,
        )
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return PrincipalResponse(
        user_id=str(user.id),
        tenant_id=str(principal.tenant_id),
        email=user.email,
        role=body.role.value,
    )
