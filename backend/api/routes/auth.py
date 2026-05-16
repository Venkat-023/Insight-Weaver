from fastapi import APIRouter, HTTPException

from schemas.auth_schemas import LoginRequest, LoginResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest) -> dict:
    username = payload.username.strip()
    password = payload.password.strip()
    if not username or not password:
        raise HTTPException(
            status_code=401,
            detail={"error": "Invalid credentials", "code": "INVALID_CREDENTIALS"},
        )
    if username.lower() == "researcher" and password == "discovery":
        return {
            "access_token": "local-demo-token",
            "token_type": "bearer",
            "user": {
                "username": username,
                "display_name": "Researcher",
                "role": "researcher",
            },
        }
    raise HTTPException(
        status_code=401,
        detail={"error": "Invalid credentials", "code": "INVALID_CREDENTIALS"},
    )
