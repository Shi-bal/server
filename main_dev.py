"""
VenomX FastAPI Backend Server - Development Mode
This version starts without AI models for testing the API structure
"""

import os
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

# Import only the antivenom router (doesn't require AI models)
from app.routers import antivenom
from app.utils.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.
    Handles startup and shutdown events.
    """
    # Startup
    logger.info("Starting VenomX FastAPI server (development mode)...")
    
    # Create temp directory if it doesn't exist
    os.makedirs("temp", exist_ok=True)
    logger.info("Temporary directory created/verified")
    
    yield
    
    # Shutdown
    logger.info("Shutting down VenomX FastAPI server...")

# Initialize FastAPI app
app = FastAPI(
    title="VenomX API (Development)",
    description="Snake identification and antivenom finder service API - Development Mode",
    version="1.0.0-dev",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers (only antivenom for now - doesn't require AI models)
app.include_router(antivenom.router, prefix="/api/v1", tags=["Antivenom Finder"])

@app.get("/")
async def root():
    """Root endpoint - health check"""
    return {
        "message": "VenomX API is running (Development Mode)",
        "version": "1.0.0-dev",
        "docs": "/docs",
        "status": "Ready for testing antivenom endpoints",
        "note": "Snake identification requires AI models to be placed in models/ directory"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "VenomX API (Development)",
        "ai_models_loaded": False,
        "available_endpoints": [
            "/api/v1/antivenom/finder",
            "/api/v1/antivenom/facilities",
            "/api/v1/antivenom/test-route"
        ]
    }

@app.get("/status")
async def status_check():
    """Extended status check"""
    import sys
    return {
        "service": "VenomX API",
        "mode": "development",
        "python_version": sys.version,
        "fastapi_ready": True,
        "database_configured": bool(settings.supabase_url),
        "ai_models_required": [
            "models/snake_detection.pt",
            "models/snake_classification.pt"
        ],
        "next_steps": [
            "1. Add AI model files to models/ directory",
            "2. Configure database password in .env",
            "3. Test endpoints at /docs"
        ]
    }

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred"
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main_dev:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )