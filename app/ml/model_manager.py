# app/ml/model_manager.py
import logging
import asyncio
from functools import lru_cache
from threading import Lock
from typing import Dict, Any
import time

from transformers import pipeline

logger = logging.getLogger(__name__)

class ModelManager:
    """Singleton class for managing ML model loading and lifecycle"""
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(ModelManager, cls).__new__(cls)
                cls._instance._models = {}
                cls._instance._model_usage = {}
                cls._instance._last_accessed = {}
                cls._instance._initialization_lock = {}
                logger.info("ModelManager singleton initialized")
            return cls._instance
    
    async def get_model(self, model_key: str) -> Any:
        """
        Get a model by key, loading it if necessary.
        Uses double-checked locking to prevent multiple initializations.
        """
        if model_key in self._models:
            self._record_usage(model_key)
            return self._models[model_key]
            
        # Use lock to prevent multiple initializations of the same model
        if model_key not in self._initialization_lock:
            self._initialization_lock[model_key] = Lock()
            
        with self._initialization_lock[model_key]:
            # Double-check after acquiring lock
            if model_key in self._models:
                self._record_usage(model_key)
                return self._models[model_key]
                
            logger.info(f"Loading model: {model_key}")
            
            # Load the model in a separate thread to avoid blocking the event loop
            model = await self._load_model_async(model_key)
            
            self._models[model_key] = model
            self._record_usage(model_key)
            return model
    
    async def _load_model_async(self, model_key: str) -> Any:
        """Load a model asynchronously using asyncio.to_thread"""
        start_time = time.time()
        
        # Define the mapping from model_key to initialization parameters
        model_configs = {
            "sentiment": {"task": "sentiment-analysis"},
            "topic": {"task": "text-classification", "model": "facebook/bart-large-mnli"},
            "language": {"task": "text-classification", "model": "papluca/xlm-roberta-base-language-detection"},
            "entity": {"task": "ner", "model": "dbmdz/bert-large-cased-finetuned-conll03-english"}
        }
        
        if model_key not in model_configs:
            raise ValueError(f"Unknown model key: {model_key}")
        
        # Use asyncio.to_thread to prevent blocking the event loop
        model = await asyncio.to_thread(
            pipeline, 
            **model_configs[model_key]
        )
        
        elapsed = time.time() - start_time
        logger.info(f"Model {model_key} loaded in {elapsed:.2f} seconds")
        return model

    def _record_usage(self, model_key: str) -> None:
        """Record model usage statistics"""
        self._last_accessed[model_key] = time.time()
        self._model_usage[model_key] = self._model_usage.get(model_key, 0) + 1
    
    async def run_model(self, model_key: str, inputs: Any) -> Any:
        """Run a model on the given inputs asynchronously"""
        model = await self.get_model(model_key)
        
        # Run the model in a separate thread
        return await asyncio.to_thread(model, inputs)
    
    async def unload_idle_models(self, idle_threshold_seconds: int = 3600) -> None:
        """Unload models that haven't been used for a specific time period"""
        current_time = time.time()
        
        for model_key in list(self._models.keys()):
            last_accessed = self._last_accessed.get(model_key, 0)
            if current_time - last_accessed > idle_threshold_seconds:
                logger.info(f"Unloading idle model: {model_key}")
                # Use lock to prevent race conditions
                with self._initialization_lock.get(model_key, Lock()):
                    if model_key in self._models:
                        del self._models[model_key]
    
    def get_model_stats(self) -> Dict[str, Any]:
        """Get statistics about model usage"""
        return {
            "loaded_models": list(self._models.keys()),
            "usage_counts": self._model_usage,
            "last_accessed": {k: time.strftime('%Y-%m-%d %H:%M:%S', 
                             time.localtime(v)) for k, v in self._last_accessed.items()}
        }

# Create a global instance that can be imported elsewhere
@lru_cache()
def get_model_manager() -> ModelManager:
    return ModelManager()