# app/posts/router.py
from fastapi import APIRouter
from app.posts.routers.classification import router as classification_router
from app.posts.routers.core import router as core_router
from app.posts.routers.search import router as search_router
from app.posts.routers.threads import router as threads_router
from app.posts.routers.user_content import router as user_content_router

router = APIRouter()

# Include all sub-routers
router.include_router(core_router, prefix="/posts", tags=["posts"])
router.include_router(classification_router, prefix="/content", tags=["content"])
router.include_router(search_router, prefix="/search", tags=["search"])
router.include_router(threads_router, prefix="/threads", tags=["threads"])
router.include_router(user_content_router, prefix="/users", tags=["user-content"])