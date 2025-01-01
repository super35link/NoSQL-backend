from fastapi import APIRouter, Depends
from .dependencies import fastapi_users, auth_backend, current_active_user
from app.db.models import User
from .schemas import UserRead, UserCreate, UserUpdate

router = APIRouter()

# Auth routes
router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    tags=["auth"]
)

router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    tags=["auth"]
)

router.include_router(
    fastapi_users.get_reset_password_router(),
    tags=["auth"]
)

# Protected route example
@router.get("/protected-route")
def protected_route(user: User = Depends(current_active_user)):
    return {"message": f"Hello {user.email}"}