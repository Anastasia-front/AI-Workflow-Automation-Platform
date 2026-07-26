from typing import Annotated

from fastapi import Depends, HTTPException
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import decode_access_token, get_db, oauth2_scheme
from app.dependencies.repositories import get_user_repository
from app.models import User
from app.repositories import UserRepository


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
) -> User:
    try:
        # Refresh tokens are also JWTs, so explicitly require an access token
        # before trusting the subject as the current API user.
        payload = decode_access_token(token)
        if payload.get("typ", "access") != "access":
            raise HTTPException(status_code=401, detail="Invalid token")
        user_id = int(payload.get("sub"))

        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = await users.get_by_id(db, int(user_id))

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user
