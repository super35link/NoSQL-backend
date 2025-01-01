from contextlib import asynccontextmanager
from fastapi import FastAPI
from app import settings
from app.auth.router import router as auth_router
from app.posts.router import router as posts_router
from app.db.mongodb import create_mongodb_indexes
from app.db.qdrant import QdrantManager

 
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await create_mongodb_indexes()
    
    # Initialize Qdrant collection
    qdrant = QdrantManager()
    await qdrant.init_collection()
    
    yield
    # Shutdown
    pass

app = FastAPI(
    title="FastAPI Users Auth",
    lifespan=lifespan
)

# Create MongoDB indexes on startup
@app.on_event("startup")
async def startup_event():
    await create_mongodb_indexes()

# Include routers
app.include_router(auth_router, prefix="/api/v1", tags=["auth"])
app.include_router(posts_router, prefix="/api/v1", tags=["posts"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)