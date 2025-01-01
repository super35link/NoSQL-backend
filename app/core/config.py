from pydantic_settings import BaseSettings
from typing import Optional
 
class Settings(BaseSettings):
    PROJECT_NAME: str = "Social Media API"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/fastapi_auth"
    SECRET_KEY: str = "your-secret-key-here"
    JWT_SECRET: str = "your-jwt-secret-here"
    COOKIE_NAME: str = "fastapi-users-token"
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "social_media"
    REDIS_URL: str = "redis://localhost:6379"  # Default for local dev
    REDIS_PASSWORD: Optional[str] = None
    REDIS_DB: int = 0
    REDIS_MAX_CONNECTIONS: int = 10  # Connection pool size

    
    # Email configuration
    MAIL_USERNAME: Optional[str] = None
    MAIL_PASSWORD: Optional[str] = None
    MAIL_FROM: Optional[str] = None
    MAIL_PORT: Optional[int] = None
    MAIL_SERVER: Optional[str] = None
    MAIL_STARTTLS: bool = False
    MAIL_SSL_TLS: bool = False
    
    
    # Optional Redis Sentinel settings if needed
    REDIS_SENTINEL_ENABLED: bool = False
    REDIS_SENTINEL_MASTER: Optional[str] = None
    REDIS_SENTINEL_NODES: Optional[str] = None
    
    # Cache TTL settings (in seconds)
    REDIS_POST_CACHE_TTL: int = 3600  # 1 hour
    REDIS_USER_CACHE_TTL: int = 3600  # 1 hour
    REDIS_RATE_LIMIT_TTL: int = 3600  # 1 hour
    

    class Config:
        env_file = ".env"

settings = Settings()