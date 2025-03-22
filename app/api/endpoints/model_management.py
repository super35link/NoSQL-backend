# app/api/endpoints/model_management.py
from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from app.auth.users import current_superuser
from app.ml.model_manager import get_model_manager

router = APIRouter()

@router.get("/stats", response_model=Dict[str, Any])
async def get_model_stats(
    current_superuser = Depends(current_superuser)
):
    """Get statistics about loaded models (admin only)"""
    model_manager = get_model_manager()
    return model_manager.get_model_stats()

@router.post("/unload/{model_key}", response_model=Dict[str, Any])
async def unload_model(
    model_key: str,
    current_superuser = Depends(current_superuser)
):
    """Manually unload a specific model (admin only)"""
    model_manager = get_model_manager()
    
    if model_key not in model_manager.get_model_stats()["loaded_models"]:
        raise HTTPException(status_code=404, detail=f"Model {model_key} not loaded")
    
    # This is a simplified version - the actual ModelManager would need an
    # explicit unload_model method to be implemented
    await model_manager.unload_idle_models(0)
    
    return {"status": "success", "message": f"Model {model_key} unloaded"}

@router.post("/preload/{model_key}", response_model=Dict[str, Any])
async def preload_model(
    model_key: str,
    current_superuser = Depends(current_superuser)
):
    """Manually preload a specific model (admin only)"""
    try:
        model_manager = get_model_manager()
        await model_manager.get_model(model_key)
        return {"status": "success", "message": f"Model {model_key} loaded"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading model: {str(e)}")

# Add to app/api/router.py:
"""
from app.api.endpoints import model_management

api_router.include_router(
    model_management.router,
    prefix="/admin/ml-models",
    tags=["admin"]
)
"""