"""
Snake identification router for VenomX API.
Handles image upload, snake detection, classification, and database lookup.
"""

import logging
import os
import time
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status
from fastapi.responses import JSONResponse

from app.models.schemas import SnakeIdResponse, ErrorResponse
from app.utils.detector import get_detector, cleanup_temp_files
from app.utils.classifier import get_classifier
from app.utils.db import db_manager
from app.utils.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/snake-id",
    response_model=SnakeIdResponse,
    responses={
        400: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        500: {"model": ErrorResponse}
    },
    summary="Identify snake species from image",
    description="""
    Upload an image of a snake to identify its species.
    
    The process:
    1. Upload image (JPG, PNG, WEBP formats supported)
    2. YOLOv8s-obb detects and crops the snake
    3. YOLOv8s classifies the cropped snake
    4. Database lookup for species information
    5. Return comprehensive results with confidence analysis
    """
)
async def identify_snake(
    image: UploadFile = File(..., description="Snake image file"),
    confidence_threshold: float = Form(
        default=0.5, 
        ge=0.0, 
        le=1.0, 
        description="Detection confidence threshold (0.0-1.0)"
    )
):
    """
    Identify snake species from uploaded image
    
    Args:
        image: Uploaded image file
        confidence_threshold: Minimum confidence for detection
        
    Returns:
        SnakeIdResponse with identification results
    """
    start_time = time.time()
    temp_files = []
    
    try:
        # Validate file
        if not image.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No file provided"
            )
        
        # Check file extension
        file_extension = image.filename.split('.')[-1].lower()
        if file_extension not in settings.allowed_extensions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file format. Allowed: {', '.join(settings.allowed_extensions)}"
            )
        
        # Check file size
        if image.size and image.size > settings.max_file_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large. Maximum size: {settings.max_file_size / (1024*1024):.1f}MB"
            )
        
        # Save uploaded file
        original_filename = f"upload_{int(time.time())}_{image.filename}"
        original_path = os.path.join(settings.temp_dir, original_filename)
        temp_files.append(original_path)
        
        try:
            with open(original_path, "wb") as buffer:
                content = await image.read()
                buffer.write(content)
            
            # Log detailed image information
            from PIL import Image as PILImage
            with PILImage.open(original_path) as pil_img:
                file_size_kb = os.path.getsize(original_path) / 1024
                logger.info(f"=== IMAGE UPLOAD INFO ===")
                logger.info(f"Original filename: {image.filename}")
                logger.info(f"Saved to: {original_path}")
                logger.info(f"ACTUAL dimensions: {pil_img.size[0]}x{pil_img.size[1]} (W x H)")
                logger.info(f"File size: {file_size_kb:.1f} KB")
                logger.info(f"Image format: {pil_img.format}")
                logger.info(f"Image mode: {pil_img.mode}")
                logger.info(f"Confidence threshold: {confidence_threshold}")
                logger.info(f"========================")
            
        except Exception as e:
            logger.error(f"Failed to save uploaded file: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save uploaded file"
            )
        
        # Step 1: Detect snake in image
        logger.info("Starting snake detection...")
        detector = get_detector()
        
        try:
            detection_result, cropped_path = detector.detect_and_crop(
                original_path, 
                confidence_threshold
            )
            
            if cropped_path:
                temp_files.append(cropped_path)
            
        except Exception as e:
            logger.error(f"Detection failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Snake detection failed: {str(e)}"
            )
        
        # Check if snake was detected
        detection_successful = detection_result.get("detected", False)
        
        if not detection_successful:
            # Return response with no detection
            processing_time = time.time() - start_time
            
            response = SnakeIdResponse(
                success=False,
                message="No snake detected in the image",
                detection_successful=False,
                detection_results=detection_result,
                cropped_image_path=None,
                classification_successful=False,
                classification_results=None,
                predictions=[],
                best_prediction=None,
                snake_info=None,
                confidence_analysis=None,
                recommendation="Please upload a clearer image of a snake",
                processing_time_seconds=round(processing_time, 2),
                image_processed=image.filename,
                model_info=detector.get_model_info()
            )
            
            # Cleanup and return
            cleanup_temp_files(temp_files)
            return response
        
        # Step 2: Classify the detected/cropped snake
        logger.info("Starting snake classification...")
        classifier = get_classifier()
        
        # Use cropped image if available, otherwise use original
        classification_image = cropped_path if cropped_path else original_path
        
        try:
            classification_result = classifier.classify_with_confidence_analysis(
                classification_image, 
                top_k=5
            )
            
        except Exception as e:
            logger.error(f"Classification failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Snake classification failed: {str(e)}"
            )
        
        classification_successful = classification_result.get("success", False)
        predictions = classification_result.get("predictions", [])
        best_prediction = classification_result.get("best_prediction")
        
        # Step 3: Database lookup for species information (for all top 5 predictions)
        snake_info = None
        
        if classification_successful and predictions:
            try:
                # Check if best_prediction is "Unknown Snake" (below 90% threshold)
                is_unknown = best_prediction and best_prediction.get("class_name") == "Unknown Snake"
                
                # Enrich all predictions with database information
                for prediction in predictions:
                    predicted_class = prediction.get("class_name")
                    
                    if predicted_class and predicted_class not in ["Unknown", "Unknown Snake"]:
                        try:
                            logger.info(f"Looking up snake info for rank {prediction['rank']}: {predicted_class}")
                            
                            # Look up by common name (which matches classifier output)
                            snake_data = await db_manager.get_snake_by_common_name(predicted_class)
                            
                            if snake_data:
                                # Update prediction with database information
                                prediction["scientific_name"] = snake_data.get("scientific_name", predicted_class)
                                prediction["image_url"] = snake_data.get("image_url")
                                
                                # If this is the best prediction AND not unknown, store its full info
                                if prediction["rank"] == 0 and best_prediction and not is_unknown:
                                    snake_info = snake_data
                                    best_prediction["scientific_name"] = snake_data.get("scientific_name", predicted_class)
                                    best_prediction["image_url"] = snake_data.get("image_url")
                                    
                                logger.info(f"Found snake info for {predicted_class}: {snake_data.get('scientific_name', 'Unknown')}")
                            else:
                                logger.warning(f"No database entry found for: {predicted_class}")
                                prediction["image_url"] = None
                                
                        except Exception as e:
                            logger.error(f"Database lookup failed for {predicted_class}: {e}")
                            prediction["image_url"] = None
                            
            except Exception as e:
                logger.error(f"Error during database lookup: {e}")
                # Don't raise exception here, just log the error
        
        # Step 4: Compile response
        processing_time = time.time() - start_time
        
        # Determine overall success
        overall_success = detection_successful and classification_successful
        
        # Create message based on confidence level
        if overall_success:
            if best_prediction:
                best_confidence = best_prediction.get('confidence', 0)
                predicted_name = best_prediction.get('class_name', 'Unknown')
                
                if predicted_name == "Unknown Snake":
                    # Below 90% threshold - show as unknown with all candidates
                    message = f"Confidence too low for definitive identification (highest: {best_confidence:.2%}). Please review all top 5 candidates carefully."
                elif best_confidence >= 0.90:
                    # High confidence (≥90%) - clear identification
                    if snake_info:
                        message = f"Snake identified as {snake_info.get('common_name', 'Unknown')} (confidence: {best_confidence:.2%}). Top 5 predictions included."
                    else:
                        message = f"Snake classified as {predicted_name} (confidence: {best_confidence:.2%}). Top 5 predictions included."
                else:
                    # This case shouldn't happen due to 90% threshold, but keeping for safety
                    message = f"Multiple possible matches detected (highest confidence: {best_confidence:.2%}). Review top 5 candidates."
            else:
                message = "Snake classification returned no results"
        else:
            message = "Snake identification incomplete"
        
        # Prepare response
        response = SnakeIdResponse(
            success=overall_success,
            message=message,
            detection_successful=detection_successful,
            detection_results=detection_result,
            cropped_image_path=cropped_path,
            classification_successful=classification_successful,
            classification_results=classification_result,
            predictions=predictions,
            best_prediction=best_prediction,
            snake_info=snake_info,
            confidence_analysis=classification_result.get("analysis"),
            recommendation=classification_result.get("analysis", {}).get("recommendation"),
            processing_time_seconds=round(processing_time, 2),
            image_processed=image.filename,
            model_info={
                "detection": detector.get_model_info(),
                "classification": classifier.get_model_info()
            }
        )
        
        logger.info(f"Snake identification completed in {processing_time:.2f}s")
        
        # Cleanup temporary files
        cleanup_temp_files(temp_files)
        
        return response
        
    except HTTPException:
        # Re-raise HTTP exceptions
        cleanup_temp_files(temp_files)
        raise
    except Exception as e:
        # Handle unexpected errors
        logger.error(f"Unexpected error in snake identification: {e}")
        cleanup_temp_files(temp_files)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during snake identification"
        )


@router.get(
    "/models/info",
    summary="Get AI model information",
    description="Get information about the loaded detection and classification models"
)
async def get_model_info():
    """Get information about the AI models"""
    try:
        detector = get_detector()
        classifier = get_classifier()
        
        return {
            "detection_model": detector.get_model_info(),
            "classification_model": classifier.get_model_info(),
            "models_loaded": True,
            "device": detector.device
        }
        
    except Exception as e:
        logger.error(f"Error getting model info: {e}")
        return {
            "error": str(e),
            "models_loaded": False
        }


@router.get(
    "/snakes",
    summary="Get all snakes from database",
    description="Retrieve all snake species from the database"
)
async def get_all_snakes():
    """Get all snakes from the database"""
    try:
        snakes = await db_manager.get_all_snakes()
        
        return {
            "success": True,
            "count": len(snakes),
            "snakes": snakes
        }
        
    except Exception as e:
        logger.error(f"Error retrieving snakes: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve snakes from database"
        )


@router.get(
    "/snakes/with-antivenom",
    summary="Get snakes that have antivenom available",
    description="Retrieve only snake species that have at least one antivenom linked (regardless of stock)"
)
async def get_snakes_with_antivenom():
    """Get snakes that have antivenom available (for dropdown in antivenom finder)"""
    try:
        snakes = await db_manager.get_snakes_with_antivenom()
        
        return {
            "success": True,
            "count": len(snakes),
            "snakes": snakes,
            "message": f"Found {len(snakes)} snake species with antivenom available"
        }
        
    except Exception as e:
        logger.error(f"Error retrieving snakes with antivenom: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve snakes with antivenom from database"
        )


@router.get(
    "/snakes/medically-significant",
    summary="Get all medically significant snakes",
    description="Retrieve all Extremely Venomous and Highly Venomous snakes (regardless of antivenom availability). Use this for snake identification dropdown to allow finding nearest facilities even without specific antivenom."
)
async def get_medically_significant_snakes():
    """
    Get all medically significant snakes (Extremely Venomous and Highly Venomous).
    This includes snakes with or without antivenom availability.
    Used for snake identification to enable fallback to nearest facilities.
    """
    try:
        snakes = await db_manager.get_medically_significant_snakes()
        
        return {
            "success": True,
            "count": len(snakes),
            "snakes": snakes,
            "message": f"Found {len(snakes)} medically significant snake species"
        }
        
    except Exception as e:
        logger.error(f"Error retrieving medically significant snakes: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve medically significant snakes from database"
        )


@router.get(
    "/snakes/{common_name}",
    summary="Get snake by common name",
    description="Retrieve snake information by common name"
)
async def get_snake_by_name(common_name: str):
    """Get snake information by common name"""
    try:
        snake = await db_manager.get_snake_by_common_name(common_name)
        
        if snake:
            return {
                "success": True,
                "snake": snake
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Snake with common name '{common_name}' not found"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving snake: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve snake from database"
        )


@router.post("/test-model")
async def test_snake_model(image: UploadFile = File(...)):
    """
    Test endpoint for the web interface - handles underscore naming convention.
    """
    try:
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
        
        # Get detector and classifier
        detector = get_detector()
        classifier = get_classifier()
        
        # Save temporary image
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
            temp_file.write(image_data)
            temp_path = temp_file.name
        
        try:
            # Detect snake
            detection_result = detector.detect_snake(temp_path)
            
            if detection_result["success"] and detection_result["detections"]:
                result["detection_success"] = True
                
                # Get the best detection
                best_detection = detection_result["detections"][0]
                result["bounding_box"] = {
                    "x1": int(best_detection["bbox"][0]),
                    "y1": int(best_detection["bbox"][1]),
                    "x2": int(best_detection["bbox"][2]),
                    "y2": int(best_detection["bbox"][3])
                }
                
                # Get cropped image path
                cropped_path = best_detection["cropped_image_path"]
                
                # Classify the cropped snake
                classification_result = classifier.classify_snake(cropped_path)
                
                if classification_result["success"]:
                    species_raw = classification_result["predicted_class"]
                    result["confidence"] = classification_result["confidence"]
                    
                    # Handle underscore naming convention
                    # Convert "Common_Mock_Viper" to "Common Mock Viper"
                    species_formatted = species_raw.replace("_", " ")
                    result["species"] = species_formatted
                    
                    # Try to find in database using the formatted name
                    try:
                        from app.utils.db import DatabaseManager
                        
                        # Try different name formats for database lookup
                        possible_names = [
                            species_formatted,  # "Common Mock Viper"
                            species_raw,        # "Common_Mock_Viper"
                            species_formatted.title(),  # "Common Mock Viper" (title case)
                        ]
                        
                        snake_info = None
                        for name_variant in possible_names:
                            snake_info = await DatabaseManager.get_snake_by_common_name(name_variant)
                            if snake_info:
                                break
                        
                        if snake_info:
                            result["snake_info"] = snake_info
                        else:
                            # Create a basic info structure if not found in database
                            result["snake_info"] = {
                                "common_name": species_formatted,
                                "scientific_name": species_formatted,
                                "fang_type": "Unknown",
                                "danger_level": "unknown",
                                "description": f"Species identified as {species_formatted}. Database information not available."
                            }
                            
                    except Exception as db_error:
                        logger.warning(f"Database lookup failed: {db_error}")
                        # Still return the classification result even if DB lookup fails
                        result["snake_info"] = {
                            "common_name": species_formatted,
                            "scientific_name": species_formatted,
                            "fang_type": "Unknown",
                            "danger_level": "unknown",
                            "description": f"Species identified as {species_formatted}. Database lookup unavailable."
                        }
                
        finally:
            # Cleanup temporary files
            try:
                os.unlink(temp_path)
                cleanup_temp_files()
            except:
                pass
        
        return result
        
    except Exception as e:
        logger.error(f"Model test error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Model testing failed: {str(e)}"
        )