from fastapi import APIRouter, status

from app.dependencies import CurrentUserDep, DbSessionDep, OAuth2PasswordFormDep
from app.schemas import (
    GoogleLoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services import AuthService

router = APIRouter()


# -------------------------------------------------
# REGISTER USER
# -------------------------------------------------
@router.post(
    "/register", 
    response_model=UserResponse, 
    status_code=status.HTTP_201_CREATED
    )
async def register(
    payload: RegisterRequest, 
    db: DbSessionDep,
):
    user = await AuthService.create_user(db, payload.email, payload.password)

    return UserResponse(
        id=user.id,
        email=user.email,
        created_at=user.created_at,
    )

# -------------------------------------------------
# LOGIN USER
# -------------------------------------------------
@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordFormDep,
    db: DbSessionDep,
):
    return await AuthService.login(db, form_data.username, form_data.password)

# -------------------------------------------------
# GOOGLE AUTH
# -------------------------------------------------
@router.post("/google", response_model=TokenResponse)
async def google_login(
    payload: GoogleLoginRequest,
    db: DbSessionDep,
):
    return await AuthService.google_login(db, payload.credential)

# -------------------------------------------------
# REFRESH TOKEN
# -------------------------------------------------
@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    payload: RefreshTokenRequest,
    db: DbSessionDep,
):
    return await AuthService.refresh_token(db, payload.refresh_token)

# -------------------------------------------------
# GET CURRENT USER
# -------------------------------------------------
@router.get("/me", response_model=UserResponse)
async def get_me(user: CurrentUserDep):
    return UserResponse(
        id=user.id,
        email=user.email,
        created_at=user.created_at,
    )
