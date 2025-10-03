"""
Configuration settings for VenomX FastAPI application.
Handles environment variables and application configuration.
"""

import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings from environment variables"""
    
    # Database Configuration
    database_url: str = Field(
        default="postgresql://postgres:password@localhost:5432/venomx",
        description="Database connection URL"
    )
    
    # Supabase Configuration
    supabase_url: str = Field(
        default="https://djhgshxjgzalqssmxsyf.supabase.co",
        description="Supabase project URL"
    )
    supabase_key: str = Field(
        default="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRqaGdzaHhqZ3phbHFzc214c3lmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTc3NTY5MjYsImV4cCI6MjA3MzMzMjkyNn0.SHfihZ6FnfqXvvlpgRaNn1Mj6OrYRwQ-BJM_uIaXvlM",
        description="Supabase anon key"
    )
    supabase_service_key: str = Field(
        default="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRqaGdzaHhqZ3phbHFzc214c3lmIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1Nzc1NjkyNiwiZXhwIjoyMDczMzMyOTI2fQ.aDRFdFX2fngSxd2JXSFc0hDy9iYpBfC4BJg97E5V_mI",
        description="Supabase service role key"
    )
    
    # OSRM Configuration
    osrm_base_url: str = Field(
        default="https://router.project-osrm.org",
        description="OSRM API base URL for routing"
    )
    
    # Model Configuration
    detection_model_path: str = Field(
        default="models/snake_detection.pt",
        description="Path to YOLOv8s-obb detection model"
    )
    classification_model_path: str = Field(
        default="models/snake_classification.pt",
        description="Path to YOLOv8s classification model"
    )
    
    # File Upload Configuration
    max_file_size: int = Field(
        default=10 * 1024 * 1024,  # 10MB
        description="Maximum file upload size in bytes"
    )
    allowed_extensions: list = Field(
        default=["jpg", "jpeg", "png", "webp"],
        description="Allowed image file extensions"
    )
    temp_dir: str = Field(
        default="temp",
        description="Temporary file storage directory"
    )
    
    # API Configuration
    api_title: str = Field(
        default="VenomX API",
        description="API title"
    )
    api_version: str = Field(
        default="1.0.0",
        description="API version"
    )
    
    # Environment
    environment: str = Field(
        default="development",
        description="Application environment (development/production)"
    )
    debug: bool = Field(
        default=True,
        description="Debug mode"
    )
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Create global settings instance
settings = Settings()


def get_database_url() -> str:
    """Get the database URL for the current environment"""
    if settings.environment == "production":
        # In production, construct from Supabase
        return f"postgresql://postgres.djhgshxjgzalqssmxsyf:[YOUR_PASSWORD]@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres"
    return settings.database_url


def is_production() -> bool:
    """Check if running in production environment"""
    return settings.environment.lower() == "production"


def get_cors_origins() -> list:
    """Get CORS origins based on environment"""
    if is_production():
        return [
            "https://venomx.app",  # Your production domain
            "https://api.venomx.app",
        ]
    return ["*"]  # Allow all origins in development