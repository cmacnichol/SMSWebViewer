import jwt
from datetime import datetime, timedelta
from fastapi import Request, Depends, HTTPException
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from app.core.config import get_settings
from app.core.database import get_session
from app.models.user import User

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
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=7)
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

    # For BASIC or OIDC, extract the token from the cookie
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        # Check for standard "Bearer " prefix if any
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
