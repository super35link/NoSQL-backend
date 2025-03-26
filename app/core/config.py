# app/core/config.py
from pydantic_settings import BaseSettings
from typing import Optional, List

class Settings(BaseSettings):
    # Project Info
    PROJECT_NAME: str = "Social Media API"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = True
    BACKEND_URL: str = "http://localhost:8000"

    # Database URLs
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/fastapi_auth"
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "social_media"
    
    # Security and JWT
    SECRET_KEY: str = "my secret"
    JWT_SECRET: str = "my secret"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60*7*24
    RESET_TOKEN_EXPIRE_MINUTES: int = 60*7*24
    COOKIE_NAME: str = "fastapi-users-token"

    # FastAPI Users (required - using uppercase as per error)
    RESET_PASSWORD_TOKEN_SECRET: str = "my secret"  # Changed from reset_password_token_secret
    VERIFICATION_TOKEN_SECRET: str = "my secret"    # Changed from verification_token_secret
    
    # Authentication Features
    VERIFY_EMAIL: bool = True
    RESET_PASSWORD: bool = True



    # Cache TTLs
    USER_CACHE_TTL: int = 3600
    POST_CACHE_TTL: int = 3600
    RATE_LIMIT_TTL: int = 3600

    # Qdrant
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333

    # Email Settings
    MAIL_USERNAME: Optional[str] = None
    MAIL_PASSWORD: Optional[str] = None
    MAIL_FROM: Optional[str] = None
    MAIL_PORT: Optional[int] = None
    MAIL_SERVER: Optional[str] = None
    MAIL_STARTTLS: bool = False
    MAIL_SSL_TLS: bool = False

    # CORS
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
    ]
    # Model Management Settings
    ENABLE_MODEL_MANAGEMENT: bool = True
    MODEL_CHECK_INTERVAL_SECONDS: int = 600  # 10 minutes
    MODEL_IDLE_THRESHOLD_SECONDS: int = 3600  # 1 hour
    
    # MongoDB Settings
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "social_media"
    MONGODB_POOL_SIZE: int = 10
    MONGODB_MAX_IDLE_TIME_MS: int = 60000  # 1 minute
    
    # Logging Configuration
    LOG_LEVEL: str = "INFO"  # Options: DEBUG, INFO, WARNING, ERROR, CRITICAL
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # API Configuration
    MAX_PAGE_SIZE: int = 100
    DEFAULT_PAGE_SIZE: int = 20
    

    class Config:
        env_file = ".env"

settings = Settings()