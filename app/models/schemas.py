"""
Pydantic models for VenomX API request and response validation.
"""

from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field
from datetime import datetime, date


# Request Models
class SnakeIdRequest(BaseModel):
    """Request model for snake identification (used for form data validation)"""
    confidence_threshold: Optional[float] = Field(
        default=0.5, 
        ge=0.0, 
        le=1.0, 
        description="Confidence threshold for detection (0.0-1.0)"
    )


class AntivenomFinderRequest(BaseModel):
    """Request model for antivenom finder - supports both mobile and web app"""
    
    # Snake identification (for mobile app - after snake ID)
    snake_common_name: Optional[str] = Field(
        None, 
        description="Common name of the snake species (mobile app use), e.g., 'Philippine Cobra'"
    )
    snake_id: Optional[int] = Field(
        None, 
        description="Snake ID from database (mobile app use)"
    )
    
    # Direct antivenom type search (for staff web app)
    antivenom_type: Optional[str] = Field(
        None,
        description="Type of antivenom: 'polyvalent' or 'monovalent' (staff web app use)"
    )
    
    # Location (required for both)
    user_latitude: float = Field(
        ..., 
        ge=-90, 
        le=90, 
        description="User's current latitude"
    )
    user_longitude: float = Field(
        ..., 
        ge=-180, 
        le=180, 
        description="User's current longitude"
    )
    
    # Distance filter (optional)
    max_distance_km: Optional[float] = Field(
        default=100, 
        gt=0, 
        description="Maximum search distance in kilometers"
    )


class FacilityListRequest(BaseModel):
    """Request model for facility listing"""
    antivenom_name: Optional[str] = Field(
        None, 
        description="Name of the antivenom to search for"
    )
    snake_id: Optional[int] = Field(
        None, 
        description="Snake ID to find antivenom for"
    )
    user_latitude: float = Field(
        ..., 
        ge=-90, 
        le=90, 
        description="User's current latitude"
    )
    user_longitude: float = Field(
        ..., 
        ge=-180, 
        le=180, 
        description="User's current longitude"
    )
    max_distance_km: Optional[float] = Field(
        default=200, 
        gt=0, 
        description="Maximum search distance in kilometers"
    )


# Response Models
class DetectionResult(BaseModel):
    """Model for snake detection result"""
    detection_id: int
    confidence: float
    class_id: int
    class_name: str
    bbox: List[float]


class ClassificationPrediction(BaseModel):
    """Model for classification prediction"""
    rank: int
    class_id: int
    class_name: str
    scientific_name: str
    confidence: float
    confidence_percentage: float
    confidence_level: Optional[str] = None


class SnakeInfo(BaseModel):
    """Model for snake information from database"""
    snake_id: int
    scientific_name: str
    common_name: Optional[str]
    fang_type: Optional[str]
    description: Optional[str]
    danger_level: Optional[str]
    image_url: Optional[str]


class RouteInfo(BaseModel):
    """Model for route/distance information"""
    success: bool
    distance_meters: Optional[float]
    distance_km: Optional[float]
    duration_seconds: Optional[float]
    duration_minutes: Optional[float]
    duration_hours: Optional[float]
    formatted_duration: Optional[str]
    start_coordinates: Optional[List[float]]
    end_coordinates: Optional[List[float]]
    fallback: Optional[bool] = False
    note: Optional[str] = None
    error: Optional[str] = None


class AntivenomInfo(BaseModel):
    """Model for antivenom information"""
    antivenom_id: int
    antivenom_name: str
    manufacturer: Optional[str]
    quantity: int
    expiration_date: Optional[date]
    batch_no: Optional[str]
    target_snakes: Optional[List[str]] = None


class FacilityInfo(BaseModel):
    """Model for facility information"""
    facility_id: int
    facility_name: str
    facility_type: str
    region: str
    province: str
    city_municipality: str
    address: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    contact_number: Optional[str]
    facility_email: Optional[str]
    antivenoms: List[AntivenomInfo]
    route_info: Optional[RouteInfo]


# Main Response Models
class SnakeIdResponse(BaseModel):
    """Response model for snake identification"""
    success: bool
    message: str
    
    # Detection results
    detection_successful: bool
    detection_results: Optional[Dict[str, Any]]
    cropped_image_path: Optional[str]
    
    # Classification results
    classification_successful: bool
    classification_results: Optional[Dict[str, Any]]
    predictions: List[ClassificationPrediction]
    best_prediction: Optional[ClassificationPrediction]
    
    # Database results
    snake_info: Optional[SnakeInfo]
    
    # Analysis
    confidence_analysis: Optional[Dict[str, Any]]
    recommendation: Optional[str]
    
    # Metadata
    processing_time_seconds: Optional[float]
    image_processed: str
    model_info: Optional[Dict[str, Any]]


class AntivenomFinderResponse(BaseModel):
    """Response model for antivenom finder"""
    success: bool
    message: str
    
    # Search parameters
    search_criteria: Dict[str, Any]
    
    # Results
    facilities_found: int
    facilities: List[FacilityInfo]
    
    # Metadata
    search_radius_km: float
    user_location: List[float]  # [lat, lon]
    processing_time_seconds: Optional[float]


class FacilityListResponse(BaseModel):
    """Response model for facility listing"""
    success: bool
    message: str
    
    # Search parameters
    search_criteria: Dict[str, Any]
    
    # Results
    facilities_found: int
    facilities: List[FacilityInfo]
    
    # Metadata
    search_radius_km: float
    user_location: List[float]  # [lat, lon]
    processing_time_seconds: Optional[float]


# Error Response Models
class ErrorResponse(BaseModel):
    """Standard error response model"""
    success: bool = False
    error: str
    message: str
    details: Optional[Dict[str, Any]] = None


class ValidationErrorResponse(BaseModel):
    """Validation error response model"""
    success: bool = False
    error: str = "Validation Error"
    message: str
    details: List[Dict[str, Any]]


# Health Check Response
class HealthCheckResponse(BaseModel):
    """Health check response model"""
    status: str
    service: str
    timestamp: datetime
    version: str
    uptime_seconds: Optional[float] = None


# Model Info Response
class ModelInfoResponse(BaseModel):
    """Model information response"""
    detection_model: Dict[str, Any]
    classification_model: Dict[str, Any]
    models_loaded: bool
    device: str