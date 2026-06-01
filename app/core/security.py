import hashlib
import jwt
from datetime import datetime, timedelta, timezone
from fastapi import Request, Depends, HTTPException
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from app.core.config import get_settings
from app.core.database import get_session
from app.models.user import User
from app.models.api_token import ApiToken

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
settings = get_settings()

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password:
        return False
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=7)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")
    return encoded_jwt

async def get_current_user(request: Request, db: AsyncSession = Depends(get_session)) -> User:
    """Dependency to retrieve the currently authenticated user."""
    # If auth is NONE, return the default admin
    if settings.AUTH_MODE.upper() == "NONE":
        res = await db.execute(select(User).where(User.role == "admin").limit(1))
        admin = res.scalar()
        if not admin:
            # Should not happen if migration ran
            raise HTTPException(status_code=401, detail="No admin user found")
        return admin

    # Check Authorization header first for API tokens
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        raw_token = auth_header[7:]
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        
        stmt = select(ApiToken).where(ApiToken.token_hash == token_hash)
        api_token = (await db.execute(stmt)).scalar_one_or_none()
        
        if api_token:
            # Check expiry if set — normalize to UTC for comparison
            if api_token.expires_at:
                expires_utc = api_token.expires_at
                if expires_utc.tzinfo is None:
                    expires_utc = expires_utc.replace(tzinfo=timezone.utc)
                if expires_utc < datetime.now(timezone.utc):
                    raise HTTPException(status_code=401, detail="API Token has expired")

            # Token is valid, lookup user
            res = await db.execute(select(User).where(User.id == api_token.user_id))
            user = res.scalar()
            if user:
                return user
                
        # If API token lookup failed, raise 401 instead of falling back to cookies
        raise HTTPException(status_code=401, detail="Invalid API Token")

    # Fallback: Extract the JWT from the cookie
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        # The cookie usually contains the raw JWT, but handle Bearer prefix just in case
        if token.startswith("Bearer "):
            token = token[7:]
            
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
        
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
        
    return user
