"""
VenomX FastAPI Backend Server
Main application entry point for snake identification and antivenom finder service.
"""

import os
import logging
from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from app.routers import snake_id, antivenom
from app.utils.db import init_db
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
    logger.info("Starting VenomX FastAPI server...")
    
    # Initialize database connection
    try:
        await init_db()
        logger.info("Database connection initialized successfully")
    except Exception as e:
        logger.warning(f"PostgreSQL pool initialization failed: {e}")
        logger.info("Continuing with Supabase client only...")
        
        # Initialize just the Supabase client
        try:
            from supabase import create_client
            from app.utils.config import settings
            
            # Set global supabase client
            import app.utils.db as db_module
            db_module.supabase = create_client(settings.supabase_url, settings.supabase_service_key)
            logger.info("Supabase client initialized successfully")
        except Exception as supabase_error:
            logger.error(f"Supabase initialization also failed: {supabase_error}")
            # Continue anyway - some endpoints might still work
    
    # Create temp directory if it doesn't exist
    os.makedirs("temp", exist_ok=True)
    logger.info("Temporary directory created/verified")
    
    yield
    
    # Shutdown
    logger.info("Shutting down VenomX FastAPI server...")

# Initialize FastAPI app
app = FastAPI(
    title="VenomX API",
    description="Snake identification and antivenom finder service API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Configure this properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(snake_id.router, prefix="/api/v1", tags=["Snake Identification"])
app.include_router(antivenom.router, prefix="/api/v1", tags=["Antivenom Finder"])

@app.get("/")
async def root():
    """Root endpoint - redirect to snake tester"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/snake_tester.html")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "VenomX API",
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.post("/test-model")
async def test_snake_model_direct(image: UploadFile = File(...)):
    """
    Direct test endpoint using the corrected OBB detection and probs classification pipeline.
    This matches the working web app implementation.
    """
    try:
        from app.utils.detector import get_detector, cleanup_temp_files
        from app.utils.classifier import get_classifier
        import tempfile
        
        # Validate file
        if not image.content_type.startswith('image/'):
            raise HTTPException(
                status_code=400,
                detail="File must be an image"
            )
        
        # Read image data
        image_data = await image.read()
        
        # Initialize result structure
        result = {
            "detection_success": False,
            "species": None,
            "confidence": None,
            "bounding_box": None,
            "snake_info": None
        }
        
        try:
            # Save temporary image
            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
                temp_file.write(image_data)
                temp_path = temp_file.name
            
            try:
                # Step 1: Detect snake with OBB and perspective transform
                detector = get_detector()
                detection_result = detector.detect_snake(temp_path)
                
                if detection_result["success"] and detection_result["detections"]:
                    result["detection_success"] = True
                    
                    # Get the best detection (first one, highest confidence)
                    best_detection = detection_result["detections"][0]
                    result["bounding_box"] = {
                        "x1": int(best_detection["bbox"][0]),
                        "y1": int(best_detection["bbox"][1]),
                        "x2": int(best_detection["bbox"][2]),
                        "y2": int(best_detection["bbox"][3])
                    }
                    
                    # Step 2: Classify the perspective-corrected crop
                    cropped_path = best_detection["cropped_image_path"]
                    classifier = get_classifier()
                    classification_result = classifier.classify(cropped_path)
                    
                    if classification_result["success"]:
                        species_name = classification_result["predicted_class"]
                        result["species"] = species_name
                        result["confidence"] = classification_result["confidence"]
                        
                        # Step 3: Look up snake in database to get reference image and details
                        from app.utils.db import db_manager
                        snake_data = None
                        try:
                            # Look up snake by common name (which matches the predicted class)
                            snake_data = await db_manager.get_snake_by_common_name(species_name)
                            if snake_data:
                                logger.info(f"Found snake in database: {snake_data.get('common_name')}")
                        except Exception as db_error:
                            logger.warning(f"Database lookup failed: {db_error}")
                        
                        # Create snake info structure with database data if available
                        if snake_data:
                            result["snake_info"] = {
                                "snake_id": snake_data.get("snake_id"),
                                "common_name": snake_data.get("common_name", species_name),
                                "scientific_name": snake_data.get("scientific_name", species_name),
                                "fang_type": snake_data.get("fang_type", "Unknown"),
                                "danger_level": snake_data.get("danger_level", "unknown"),
                                "description": snake_data.get("description", f"Species identified as {species_name}"),
                                "reference_image_url": snake_data.get("image_url"),  # Include reference image
                            }
                        else:
                            result["snake_info"] = {
                                "common_name": species_name,
                                "scientific_name": species_name,
                                "fang_type": "Unknown",
                                "danger_level": "unknown",
                                "description": f"Species identified as {species_name} with {(result['confidence']*100):.1f}% confidence using OBB detection and perspective-corrected classification.",
                                "reference_image_url": None,
                            }
                        
                        logger.info(f"Pipeline success: {species_name} ({result['confidence']:.3f})")
                    else:
                        result["snake_info"] = {
                            "common_name": "Classification Failed",
                            "scientific_name": "Unknown",
                            "fang_type": "Unknown",
                            "danger_level": "unknown",
                            "description": f"Detection successful but classification failed: {classification_result.get('error', 'Unknown error')}"
                        }
                else:
                    result["snake_info"] = {
                        "common_name": "No Snake Detected",
                        "scientific_name": "Unknown",
                        "fang_type": "Unknown",
                        "danger_level": "unknown",
                        "description": detection_result.get("message", "No snake found in the image")
                    }
                
            finally:
                # Cleanup temporary files
                try:
                    os.unlink(temp_path)
                    cleanup_temp_files()
                except:
                    pass
                    
        except Exception as model_error:
            logger.error(f"Model processing error: {model_error}")
            import traceback
            traceback.print_exc()
            result["snake_info"] = {
                "common_name": "Processing Error",
                "scientific_name": "Error",
                "fang_type": "Unknown",
                "danger_level": "unknown",
                "description": f"Model processing failed: {str(model_error)}"
            }
        
        return result
        
    except Exception as e:
        logger.error(f"Test endpoint error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "detection_success": False,
            "species": "Error",
            "confidence": 0.0,
            "bounding_box": None,
            "snake_info": {
                "common_name": "Error",
                "scientific_name": "Error",
                "fang_type": "Unknown",
                "danger_level": "unknown",
                "description": f"Endpoint error: {str(e)}"
            }
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
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )