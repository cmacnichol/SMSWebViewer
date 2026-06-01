from datetime import datetime, timedelta, timezone
from typing import Any, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from authlib.integrations.starlette_client import OAuth

from app.core.config import get_settings
from app.core.database import get_session
from app.core.security import (
    create_access_token,
    verify_password,
    get_current_user,
    get_password_hash
)
from pydantic import BaseModel, Field
from app.models.user import User
from app.models.api_token import ApiToken
import hashlib
import secrets

settings = get_settings()
router = APIRouter(prefix="/api/user", tags=["user_auth"])

# Configure OAuth for OIDC
oauth = OAuth()
if settings.AUTH_MODE.upper() == "OIDC" and settings.OIDC_ISSUER_URL:
    oauth.register(
        name='oidc',
        server_metadata_url=settings.OIDC_ISSUER_URL,
        client_id=settings.OIDC_CLIENT_ID,
        client_secret=settings.OIDC_CLIENT_SECRET,
        client_kwargs={'scope': 'openid profile email'}
    )

class CreateUserRequest(BaseModel):
    username: str
    password: str = Field(min_length=8)
    role: str = Field(default="user")

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)

class CreateTokenRequest(BaseModel):
    description: str = "Generated API Token"
    is_global: bool = False
    expires_in_days: Optional[int] = Field(default=None, ge=1, le=3650, description="Token lifetime in days. Omit for non-expiring tokens.")


@router.post("/login")
async def login_basic(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_session)
) -> Any:
    """Basic Auth login endpoint."""
    if settings.AUTH_MODE.upper() != "BASIC":
        raise HTTPException(status_code=400, detail="Basic auth is not enabled")
        
    res = await db.execute(select(User).where(User.username == form_data.username))
    user = res.scalar()
    
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
        
    # Create token
    access_token = create_access_token(data={"sub": user.id}, expires_delta=timedelta(days=7))
    
    # Set HTTP-Only cookie
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=7 * 24 * 60 * 60,  # 7 days
        samesite="lax",
    )
    return {"message": "Logged in successfully"}


@router.get("/oidc/login")
async def login_oidc(request: Request):
    """Redirects to OIDC provider."""
    if settings.AUTH_MODE.upper() != "OIDC":
        raise HTTPException(status_code=400, detail="OIDC auth is not enabled")
    redirect_uri = f"{request.url.scheme}://{request.headers.get('host')}/api/user/oidc/callback"
    return await oauth.oidc.authorize_redirect(request, redirect_uri)


@router.get("/oidc/callback")
async def auth_oidc_callback(request: Request, db: AsyncSession = Depends(get_session)):
    """Process OIDC callback and log the user in."""
    if settings.AUTH_MODE.upper() != "OIDC":
        raise HTTPException(status_code=400, detail="OIDC auth is not enabled")
        
    token = await oauth.oidc.authorize_access_token(request)
    user_info = token.get('userinfo')
    if not user_info:
        raise HTTPException(status_code=400, detail="No userinfo received from OIDC")
        
    sub = user_info.get("sub")
    email = user_info.get("email") or sub
    
    res = await db.execute(select(User).where(User.oidc_sub == sub))
    user = res.scalar()
    
    # Auto-provision user if they don't exist
    if not user:
        user = User(
            id=str(uuid.uuid4()),
            username=email,
            oidc_sub=sub,
            role="user"
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
    # Create session cookie
    access_token = create_access_token(data={"sub": user.id}, expires_delta=timedelta(days=7))
    
    response = RedirectResponse(url="/")
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=7 * 24 * 60 * 60,
        samesite="lax",
    )
    return response


@router.post("/logout")
async def logout(response: Response):
    """Clear session cookie."""
    response.delete_cookie("access_token", httponly=True, samesite="lax")
    return {"message": "Logged out successfully"}


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current logged in user details."""
    return {
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
        "auth_mode": settings.AUTH_MODE.upper()
    }


@router.put("/password")
async def change_password(
    req: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Change password for the current user."""
    if not current_user.password_hash or not verify_password(req.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect current password")
        
    current_user.password_hash = get_password_hash(req.new_password)
    db.add(current_user)
    await db.commit()
    return {"message": "Password updated successfully"}


@router.get("/all")
async def list_users(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """List all users (Admins only)."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    stmt = select(User)
    users = (await db.execute(stmt)).scalars().all()
    return [{"id": u.id, "username": u.username, "role": u.role} for u in users]


@router.post("/create")
async def create_user(
    req: CreateUserRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Create a new user (Admins only)."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Check if exists
    res = await db.execute(select(User).where(User.username == req.username))
    if res.scalar():
        raise HTTPException(status_code=400, detail="Username already exists")
    
    new_user = User(
        id=str(uuid.uuid4()),
        username=req.username,
        password_hash=get_password_hash(req.password),
        role=req.role
    )
    db.add(new_user)
    await db.commit()
    return {"message": "User created successfully"}


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Delete a user (Admins only)."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    
    stmt = select(User).where(User.id == user_id)
    target_user = (await db.execute(stmt)).scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if target_user.role == "admin":
        res = await db.execute(select(User).where(User.role == "admin"))
        admins = res.scalars().all()
        if len(admins) <= 1:
            raise HTTPException(status_code=400, detail="Cannot delete the last admin")
            
    await db.delete(target_user)
    await db.commit()
    return {"message": "User deleted"}


@router.get("/tokens")
async def list_tokens(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_session)):
    """List API tokens for the current user."""
    stmt = select(ApiToken).where(ApiToken.user_id == current_user.id)
    tokens = (await db.execute(stmt)).scalars().all()
    return [{"id": t.id, "created_at": t.created_at, "is_global": t.is_global, "description": t.description} for t in tokens]


@router.post("/tokens")
async def create_token(
    req: CreateTokenRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Generate a new API token. Only admins can generate global tokens."""
    if req.is_global and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can create global tokens")
        
    raw_token = "mcp_" + secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    expires_at = None
    if req.expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=req.expires_in_days)
    
    new_token = ApiToken(
        user_id=current_user.id,
        token_hash=token_hash,
        is_global=req.is_global,
        description=req.description,
        expires_at=expires_at,
    )
    db.add(new_token)
    await db.commit()
    
    return {
        "message": "Token generated successfully. Save it now, you won't be able to see it again.",
        "token": raw_token,
        "expires_at": expires_at.isoformat() if expires_at else None,
    }


@router.delete("/tokens/all")
async def revoke_all_tokens(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Revoke ALL API tokens for the current user."""
    stmt = select(ApiToken).where(ApiToken.user_id == current_user.id)
    tokens = (await db.execute(stmt)).scalars().all()
    for token in tokens:
        await db.delete(token)
    await db.commit()
    return {"message": f"Revoked {len(tokens)} token(s) successfully."}


@router.delete("/tokens/{token_id}")
async def revoke_token(
    token_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Revoke an API token."""
    stmt = select(ApiToken).where(ApiToken.id == token_id)
    token = (await db.execute(stmt)).scalar_one_or_none()
    
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
        
    if token.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to revoke this token")
        
    await db.delete(token)
    await db.commit()
    return {"message": "Token revoked"}
