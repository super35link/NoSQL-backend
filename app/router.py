# app/posts/router.py
from fastapi import APIRouter

from app.api.endpoints import model_management
from .posts.routers.classification_routes import router as classification_router
from .posts.routers.hashtag_routes import router as hashtag_router
from .posts.routers.search_routes import router as search_router
from .posts.routers.threads_routes import router as threads_router
from .posts.routers.engagement_routes import router as engagement_router

# app/api/router.py (Main Router)
from app.auth.router import router as auth_router
from app.profile.router import router as profile_router

from app.follow.router import router as follow_router
from app.settings.router import router as settings_router

# Create posts router
router = APIRouter()

# Include all posts-related routers
router.include_router(hashtag_router)            # Will be at /api/v1/posts/...
router.include_router(classification_router)         # Will be at /api/v1/posts/content/...
router.include_router(search_router)                # Will be at /api/v1/posts/search/...
router.include_router(threads_router)               # Will be at /api/v1/posts/threads/...
router.include_router(engagement_router)            # Will be at /api/v1/posts/engagement/...

# Create main API router
api_router = APIRouter()

# Include all sub-routers WITHOUT /api/v1 prefix (it's added in main.py)
api_router.include_router(auth_router)              # Will be at /api/v1/auth/...
api_router.include_router(profile_router)           # Will be at /api/v1/profile/...
api_router.include_router(follow_router)            # Will be at /api/v1/follow/...
api_router.include_router(settings_router)          # Will be at /api/v1/settings/...


# Include admin model management router
api_router.include_router(
    model_management.router,
    prefix="/admin/ml-models",
    tags=["admin"]
)