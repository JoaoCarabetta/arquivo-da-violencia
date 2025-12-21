"""Authentication router."""

from datetime import timedelta
from fastapi import APIRouter, HTTPException, status

from app.auth import (
    authenticate_user,
    create_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    LoginRequest,
    Token,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token)
async def login(request: LoginRequest):
    """
    Login endpoint that returns a JWT token.
    
    Default credentials:
    - username: admin (from ADMIN_USERNAME env var)
    - password: admin123 (from ADMIN_PASSWORD env var)
    """
    if not authenticate_user(request.username, request.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": request.username},
        expires_delta=access_token_expires
    )
    
    return Token(access_token=access_token)


@router.post("/verify")
async def verify_token(token: str):
    """Verify if a token is valid."""
    from app.auth import decode_access_token
    
    try:
        token_data = decode_access_token(token)
        return {"valid": True, "username": token_data.username}
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

