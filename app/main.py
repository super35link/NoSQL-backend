# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.db.mongodb import create_mongodb_indexes
from app.db.qdrant import QdrantManager
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.router import api_router
from fastapi.routing import APIRoute
from typing import Set, List
 
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events"""
    try:
        # Startup
        print("Starting up application services...")
        await create_mongodb_indexes()
        
        # Initialize Qdrant collection
        qdrant = QdrantManager()
        await qdrant.init_collection()
        
        print("All services started successfully")
        yield
        
    except Exception as e:
        print(f"Error during startup: {e}")
        raise
    finally:
        # Shutdown
        print("Shutting down application...")

async def internal_error_handler(request: Request, exc: Exception):
    """Global exception handler for internal server errors"""
    error_msg = f"Internal Server Error: {str(exc)}"
    print(f"{error_msg}\nRequest path: {request.url.path}")
    return JSONResponse(
        status_code=500,
        content={
            "detail": str(exc),
            "type": type(exc).__name__
        }
    )

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Social Media API with FastAPI",
    version="1.0.0",
    lifespan=lifespan,
    debug=settings.DEBUG
)

# Add error handler
app.add_exception_handler(Exception, internal_error_handler)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,  # Cache preflight requests for 1 hour
)

# Mount all routes under /api/v1
app.include_router(api_router, prefix="/api/v1")

print("\nAll registered routes:")
for route in app.routes:
    if isinstance(route, APIRoute):
        path: str = route.path
        methods: Set[str] = route.methods
        name: str = route.name or ""
        tags: List[str] = list(getattr(route, "tags", []))
        
        print(f"\nPath: {path}")
        print(f"Methods: {methods}")
        print(f"Name: {name}")
        print(f"Tags: {tags}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,  # Enable auto-reload in debug mode
        log_level="debug" if settings.DEBUG else "info"
    )