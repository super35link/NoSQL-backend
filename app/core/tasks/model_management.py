# app/core/tasks/model_management.py
import asyncio
import logging
from datetime import datetime
from app.ml.model_manager import get_model_manager

logger = logging.getLogger(__name__)

async def model_management_task(
    check_interval_seconds: int = 600,  # 10 minutes
    idle_threshold_seconds: int = 3600,  # 1 hour
):
    """
    Background task that manages model lifecycle:
    - Unloads idle models to free memory
    - Logs model usage statistics
    - Performs health checks
    """
    model_manager = get_model_manager()
    
    while True:
        try:
            logger.info("Running model management task")
            
            # Unload idle models
            await model_manager.unload_idle_models(idle_threshold_seconds)
            
            # Log model usage statistics
            stats = model_manager.get_model_stats()
            logger.info(f"Model stats: {stats}")
            
            # Wait for next check interval
            await asyncio.sleep(check_interval_seconds)
            
        except Exception as e:
            logger.error(f"Error in model management task: {e}")
            await asyncio.sleep(60)  # Wait a minute before retrying on error

# Add this to app/main.py lifespan function
"""
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        # Startup
        print("Starting up application services...")
        await create_mongodb_indexes()
        
        # Initialize Qdrant collection
        qdrant = QdrantManager()
        await qdrant.init_collection()
        
        # Start model management task
        model_management_task = asyncio.create_task(model_management_task())
        
        print("All services started successfully")
        yield
        
    except Exception as e:
        print(f"Error during startup: {e}")
        raise
    finally:
        # Shutdown
        print("Shutting down application...")
        # Cancel any running tasks
        for task in asyncio.all_tasks():
            if task is not asyncio.current_task(): 
                task.cancel()
"""