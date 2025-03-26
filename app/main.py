# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.db.mongodb import create_mongodb_indexes, get_mongodb
from app.db.qdrant import QdrantManager
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.router import api_router
from fastapi.routing import APIRoute
from typing import Set, List
import logging
import asyncio
from app.ml.model_manager import get_model_manager
from app.core.tasks.model_management import model_management_task

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events"""
    # Keep track of background tasks for proper shutdown
    background_tasks = []
    
    try:
        # Startup
        logger.info("Starting up application services...")
        
        # Initialize MongoDB
        logger.info("Initializing MongoDB indexes...")
        db = get_mongodb()
        await create_mongodb_indexes()
        logger.info("MongoDB indexes created successfully")
        
        # Initialize Qdrant 
        logger.info("Initializing Qdrant vector database...")
        qdrant = QdrantManager()
        await qdrant.init_collection()
        logger.info("Qdrant initialized successfully")
        
        # Start model management background task
        if settings.ENABLE_MODEL_MANAGEMENT:
            logger.info("Starting model management background task...")
            model_mgmt_task = asyncio.create_task(
                model_management_task(
                    check_interval_seconds=settings.MODEL_CHECK_INTERVAL_SECONDS,
                    idle_threshold_seconds=settings.MODEL_IDLE_THRESHOLD_SECONDS
                )
            )
            model_mgmt_task.set_name("model_management_task")
            background_tasks.append(model_mgmt_task)
            logger.info("Model management task started")
        
        logger.info("All services started successfully")
        yield
        
    except Exception as e:
        logger.error(f"Error during startup: {e}", exc_info=True)
        # We still yield to allow the application to start with degraded functionality
        yield
    finally:
        # Shutdown
        logger.info("Shutting down application...")
        
        # Cancel background tasks
        for task in background_tasks:
            if not task.done():
                logger.info(f"Cancelling task: {task.get_name()}")
                task.cancel()
                
        # Wait for tasks to complete cancellation
        if background_tasks:
            logger.info("Waiting for background tasks to complete cancellation...")
            await asyncio.gather(*background_tasks, return_exceptions=True)
            
        logger.info("Application shutdown completed")

async def internal_error_handler(request: Request, exc: Exception):
    """Global exception handler for internal server errors"""
    error_msg = f"Internal Server Error: {str(exc)}"
    logger.error(f"{error_msg}\nRequest path: {request.url.path}", exc_info=True)
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

# Log all registered routes during startup
def log_routes():
    """Log all registered routes"""
    logger.info("Registered routes:")
    for route in app.routes:
        if isinstance(route, APIRoute):
            path: str = route.path
            methods: Set[str] = route.methods
            name: str = route.name or ""
            tags: List[str] = list(getattr(route, "tags", []))
            
            logger.debug(f"Path: {path}")
            logger.debug(f"Methods: {methods}")
            logger.debug(f"Name: {name}")
            logger.debug(f"Tags: {tags}")

# Log routes during startup
log_routes()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,  # Enable auto-reload in debug mode
        log_level="debug" if settings.DEBUG else "info"
    )