# app/api/router.py (Main Router)
from fastapi import APIRouter
from app.auth.router import router as auth_router
from app.profile.router import router as profile_router
from app.posts.router import router as posts_router
from app.follow.router import router as follow_router
from app.settings.router import router as settings_router
from app.posts.routers.hashtag import router as hashtag_router

# Create main API router
api_router = APIRouter()

# Include all sub-routers WITHOUT /api/v1 prefix (it's added in main.py)
api_router.include_router(auth_router)              # Will be at /api/v1/auth/...
api_router.include_router(profile_router)           # Will be at /api/v1/profile/...
api_router.include_router(posts_router)             # Will be at /api/v1/posts/...
api_router.include_router(follow_router)            # Will be at /api/v1/follow/...
api_router.include_router(settings_router)          # Will be at /api/v1/settings/...
api_router.include_router(hashtag_router)           # Will be at /api/v1/hashtags/..