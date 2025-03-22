# app/auth/dependencies.py
from typing import AsyncGenerator
from fastapi import Depends
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import User
from app.db.base import get_async_session
from .manager import UserManager

async def get_user_db(
    session: AsyncSession = Depends(get_async_session)
) -> AsyncGenerator[SQLAlchemyUserDatabase, None]:
    yield SQLAlchemyUserDatabase(session, User)

async def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db)
) -> AsyncGenerator[UserManager, None]:
    yield UserManager(user_db)