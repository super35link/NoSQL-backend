# app/users/services/user_service.py
from typing import Dict, Any, Optional, List
import logging
from app.db.mongodb import get_mongodb
from app.db.base import get_async_session
from app.auth.users import fastapi_users

logger = logging.getLogger(__name__)

class UserService:
    """Service for user-related operations"""
    
    def __init__(self):
        self.db = None
        
    async def _ensure_db(self) -> None:
        """Ensure MongoDB connection is initialized."""
        if not self.db:
            self.db = await get_mongodb()
            
    async def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Get user from SQL database and convert to dictionary format
        for consistent usage with MongoDB documents
        """
        try:
            # Use FastAPI-Users to get the user from the SQL database
            async for session in get_async_session():
                user = await fastapi_users.get_user_manager().get_by_id(user_id, session)
                
                if not user:
                    return None
                    
                # Convert SQLAlchemy model to dictionary
                user_dict = {
                    "id": user.id,
                    "email": user.email,
                    "username": user.username,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "is_active": user.is_active,
                    "is_verified": user.is_verified,
                    "is_superuser": user.is_superuser,
                    "created_at": user.created_at,
                    "updated_at": user.updated_at
                }
                
                return user_dict
                
        except Exception as e:
            logger.error(f"Error fetching user by ID {user_id}: {e}")
            return None
    
    async def get_users_by_ids(self, user_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        """
        Get multiple users by their IDs and return as a dictionary 
        mapping user_id to user data
        """
        user_map = {}
        
        # Create a set of unique user IDs
        unique_ids = set(user_ids)
        
        async for session in get_async_session():
            for user_id in unique_ids:
                try:
                    user = await fastapi_users.get_user_manager().get_by_id(user_id, session)
                    if user:
                        user_map[user_id] = {
                            "id": user.id,
                            "email": user.email,
                            "username": user.username,
                            "first_name": user.first_name,
                            "last_name": user.last_name,
                            "is_active": user.is_active,
                            "is_verified": user.is_verified,
                            "is_superuser": user.is_superuser,
                            "created_at": user.created_at,
                            "updated_at": user.updated_at
                        }
                except Exception as e:
                    logger.error(f"Error fetching user by ID {user_id}: {e}")
                    # Continue with next user
        
        return user_map

    async def cache_user_data(self, user_id: int, user_data: Dict[str, Any]) -> bool:
        """Cache user data in MongoDB for faster access"""
        await self._ensure_db()
        
        try:
            # Remove sensitive data before caching
            if "hashed_password" in user_data:
                del user_data["hashed_password"]
                
            # Add timestamp
            from datetime import datetime
            user_data["cached_at"] = datetime.utcnow()
            
            await self.db.user_cache.update_one(  # type: ignore
                {"user_id": user_id},
                {"$set": user_data},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error caching user data: {e}")
            return False

# Instance for dependency injection
user_service = UserService()