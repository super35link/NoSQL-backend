from sqlalchemy import Column, Integer, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import relationship
from app.db.base import Base

class Follow(Base):
    __tablename__ = "follows"

    id = Column(Integer, primary_key=True)
    follower_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    following_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint('follower_id', 'following_id', name='unique_follows'),
    )

    # Relationships without circular references
    follower = relationship(
        "User",
        foreign_keys=[follower_id],
        back_populates="user_follows"
    )
    following = relationship(
        "User",
        foreign_keys=[following_id],
        back_populates="user_followers"
    )