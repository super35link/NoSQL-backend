# app/db/models.py
from datetime import datetime
from typing import Optional
from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTable
from sqlalchemy import Integer, String, DateTime, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from sqlalchemy.ext.asyncio import AsyncSession

class User(SQLAlchemyBaseUserTable[int], Base):
    __tablename__ = "users"

    # Override the id field to use Integer instead of UUID
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Required by FastAPI-Users
    email: Mapped[str] = mapped_column(String(length=320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(length=1024), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Additional fields
    username: Mapped[str] = mapped_column(String(length=30), unique=True, index=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(length=50), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(length=50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True
    )
    async def ensure_settings(self, session: AsyncSession) -> None:
        """Ensure user has associated settings"""
        if not self.settings:
            from app.settings.models import Settings
            self.settings = Settings(user_id=self.id)
            session.add(self.settings)
            await session.commit()
