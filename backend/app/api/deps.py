"""FastAPI dependencies: authenticate the bearer token into a Principal and gate by role."""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from app.org import permissions
from app.security import (
    AuthError,
    Principal,
    decode_supabase_claims,
    decode_token,
    oidc_identity_from_claims,
    supabase_identity_from_claims,
    verify_oidc_claims,
)

_bearer = HTTPBearer(auto_error=True)

# Roles permitted to trigger an agent run (vs. read-only viewers). A department 'lead' is a superset
# of an analyst (can run + propose) that additionally clears the approver gate (require_lead_or_admin).
RUNNER_ROLES = {"admin", "analyst", "lead"}

# Roles permitted to APPROVE/EXECUTE/UNDO/REJECT a write (ADR 0007 + per-employee approval). The
# per-department + money/legal authorization is enforced at the service layer (authorize_approver).
APPROVER_ROLES = {"admin", "lead"}


async def _resolve_principal(
    *, auth_user_id, email: str, aal: str, user_id=None
) -> Principal:
    """Shared directory resolution: a verified IdP identity -> a Principal whose tenant + role come
    ONLY from the user_memberships directory (never the token). `user_id` overrides the audit id for
    external IdPs whose subject isn't the membership's auth_user_id."""
    from app.repositories import memberships  # local import: keeps pure-test imports DB-free

    membership = await memberships.resolve(auth_user_id=auth_user_id, email=email)
    if membership is None:
        raise AuthError("no active membership for this account — ask the operator for an invite")
    return Principal(
        tenant_id=membership.tenant_id,
        user_id=user_id or auth_user_id,
        email=email or membership.email,
        role=membership.role,
        aal=aal,
        department=membership.department,
        person_id=str(membership.person_id) if membership.person_id else None,
    )


async def _principal_from_supabase(token: str) -> Principal:
    """Verify a Supabase access token, then resolve tenant + role from the membership directory."""
    claims = decode_supabase_claims(token)
    auth_user_id, email, aal = supabase_identity_from_claims(claims)
    return await _resolve_principal(auth_user_id=auth_user_id, email=email, aal=aal)


async def _principal_from_jwks(token: str) -> Principal:
    """Verify an external-IdP token, then resolve tenant + role from the directory (NOT the token's
    self-asserted claims). aal comes from mapped MFA evidence in the token."""
    settings = get_settings()
    claims = verify_oidc_claims(token, settings)
    user_id, email, aal = oidc_identity_from_claims(claims, settings)
    if not email:
        raise AuthError("token missing 'email' — cannot resolve a membership")
    # External subjects aren't the directory's auth_user_id; resolve by email, audit as user_id.
    return await _resolve_principal(auth_user_id=user_id, email=email, aal=aal, user_id=user_id)


async def get_principal(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> Principal:
    settings = get_settings()
    token = credentials.credentials
    try:
        mode = settings.auth_mode.lower()
        if mode == "supabase":
            return await _principal_from_supabase(token)
        if mode == "jwks":
            return await _principal_from_jwks(token)
        # HS256 dev tokens are accepted ONLY when ENV=dev. A production service that forgot to set
        # AUTH_MODE=jwks/supabase must NEVER fall through to HS256 verification — that would accept any
        # token signed with the (possibly default/leaked) jwt_secret and forge a privileged principal.
        if not settings.is_dev:
            if settings.supabase_auth_configured:
                return await _principal_from_supabase(token)
            raise AuthError(f"auth_mode '{mode}' is invalid in production — set AUTH_MODE=jwks or supabase")
        try:
            return decode_token(token)  # dev (HS256), ENV=dev only
        except AuthError:
            # Hybrid: in dev mode, real Supabase logins are also accepted when configured, so the
            # public demo (dev tokens) and real customer/operator logins coexist on one service.
            if settings.supabase_auth_configured:
                return await _principal_from_supabase(token)
            raise
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def require_runner(principal: Principal = Depends(get_principal)) -> Principal:
    if principal.role not in RUNNER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"role '{principal.role}' may not trigger runs",
        )
    return principal


async def require_unrestricted(principal: Principal = Depends(get_principal)) -> Principal:
    """Leadership / operator tier — an unrestricted principal (no department scope), the same bar as
    the executive view. Department-scoped logins are refused. Used for cross-cutting governance reads
    (e.g. the learning approval queue / drift) that aren't a single agent's data."""
    if permissions.allowed_agents(principal.role, principal.department) is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"department '{principal.department}' does not include this view",
        )
    return principal


def require_agent_access(agent_name: str):
    """Dependency factory: the principal's department must include this agent.

    Admin role / no department (executive) = unrestricted; unknown departments fail closed —
    the maps live in app/org/permissions.py. Enforcement is server-side; the UI only mirrors it.
    """

    async def _check(principal: Principal = Depends(get_principal)) -> Principal:
        if not permissions.can_use_agent(principal.role, principal.department, agent_name):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"department '{principal.department}' does not include the {agent_name} agent",
            )
        return principal

    return _check


def require_agent_runner(agent_name: str):
    """require_agent_access + the existing runner-role gate (admin/analyst) for run routes."""
    agent_access = require_agent_access(agent_name)

    async def _check(principal: Principal = Depends(agent_access)) -> Principal:
        if principal.role not in RUNNER_ROLES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"role '{principal.role}' may not trigger runs",
            )
        return principal

    return _check


async def require_admin(principal: Principal = Depends(get_principal)) -> Principal:
    """Operator tier: only admins may use operator tools (memberships, ads/CRM, learning) — and admin
    access additionally requires a verified second factor (aal2 / TOTP 2FA)."""
    if principal.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"role '{principal.role}' may not perform this operation",
        )
    if principal.aal != "aal2":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="operator access requires 2FA (aal2) — enroll a TOTP factor in Security settings",
        )
    return principal


async def require_lead_or_admin(principal: Principal = Depends(get_principal)) -> Principal:
    """Approve/execute/undo/reject a write (ADR 0007 + per-employee approval): a department LEAD or an
    admin, AND a verified second factor (aal2). The per-department + money/legal authorization is then
    enforced at the service layer (authorize_approver) against the action's OWNING agent. Keeping the
    2FA bar here means a money/legal approval stays 2FA-gated for leads exactly as it was for admins."""
    if principal.role not in APPROVER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"role '{principal.role}' may not approve or execute actions",
        )
    if principal.aal != "aal2":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="approving an action requires 2FA (aal2) — enroll a TOTP factor in Security settings",
        )
    return principal
