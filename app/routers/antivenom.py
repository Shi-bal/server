import logging
import time
import asyncio
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, status, Query, Body
from fastapi.responses import JSONResponse

from app.models.schemas import (
    AntivenomFinderRequest, 
    AntivenomFinderResponse,
    FacilityListRequest,
    FacilityListResponse,
    ErrorResponse,
    FacilityInfo,
    AntivenomInfo,
    RouteInfo
)
from app.utils.db import db_manager
from app.utils.osrm import get_osrm_client
from app.utils.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/antivenom/finder",
    response_model=AntivenomFinderResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse}
    },
    summary="Find facilities with antivenom (Mobile App & Staff Web App)",
    description="""
    Unified endpoint for finding healthcare facilities with antivenom.
    
    **Mobile App Use Case:**
    - After snake identification, provide `snake_id` or `snake_common_name`
    - Get nearest facilities with required antivenom
    - Returns facilities sorted by distance
    
    **Staff Web App Use Case:**
    - Search by `antivenom_type` directly ('polyvalent' or 'monovalent')
    - Get facilities for map display with coordinates
    - Returns facilities with complete location data for OpenStreetMap
    
    The process:
    1. Search by snake (mobile) OR antivenom name (staff)
    2. Apply optional filters (location, distance, facility type)
    3. Calculate distance and travel time to each facility
    4. Return sorted list by distance (nearest first)
    """
)
async def find_antivenom(request: AntivenomFinderRequest):
    """
    Find facilities with antivenom - unified endpoint for mobile and web
    
    Args:
        request: AntivenomFinderRequest with search criteria
        
    Returns:
        AntivenomFinderResponse with facility list
    """
    start_time = time.time()
    
    try:
        # Validate input - need either snake info OR antivenom type
        if not request.snake_common_name and not request.snake_id and not request.antivenom_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either snake_common_name, snake_id, or antivenom_type must be provided"
            )
        
        facilities_data = []
        snake_id = None
        snake_info = None
        
        # CASE 1: Mobile App - Search by Snake (after identification)
        if request.snake_id or request.snake_common_name:
            # Step 1: Get snake_id if common name provided
            snake_id = request.snake_id
            
            if request.snake_common_name and not snake_id:
                try:
                    snake_info = await db_manager.get_snake_by_common_name(request.snake_common_name)
                    if snake_info:
                        snake_id = snake_info["snake_id"]
                    else:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Snake species '{request.snake_common_name}' not found in database"
                        )
                except HTTPException:
                    raise
                except Exception as e:
                    logger.error(f"Error looking up snake: {e}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to lookup snake species"
                    )
            
            # Step 2: Find facilities with antivenom for this snake
            logger.info(f"Finding facilities with antivenom for snake_id: {snake_id}")
            
            try:
                facilities_data = await db_manager.get_facilities_with_antivenom(snake_id)
            except Exception as e:
                logger.error(f"Error finding facilities: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to find facilities with antivenom"
                )
        
        # CASE 2: Staff Web App - Search by Antivenom Type
        elif request.antivenom_type:
            logger.info(f"Finding facilities with antivenom type: {request.antivenom_type}")
            
            # Validate antivenom type
            if request.antivenom_type not in ['polyvalent', 'monovalent']:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="antivenom_type must be 'polyvalent' or 'monovalent'"
                )
            
            try:
                facilities_data = await db_manager.get_facilities_by_antivenom_type(
                    antivenom_type=request.antivenom_type
                )
            except Exception as e:
                logger.error(f"Error finding facilities by antivenom type: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to find facilities with antivenom type"
                )
        
        # Check if any facilities found
        if not facilities_data:
            # FALLBACK: Only for mobile app (snake searches)
            # Web app (antivenom_type searches) should NOT use fallback
            if request.antivenom_type:
                # Web app search - no fallback, just return message
                processing_time = time.time() - start_time
                return AntivenomFinderResponse(
                    success=True,
                    message=f"No facilities found with {request.antivenom_type} antivenom",
                    search_criteria={
                        "snake_id": snake_id,
                        "snake_common_name": request.snake_common_name,
                        "antivenom_type": request.antivenom_type,
                        "user_location": [request.user_latitude, request.user_longitude],
                        "max_distance_km": request.max_distance_km
                    },
                    facilities_found=0,
                    facilities=[],
                    search_radius_km=request.max_distance_km,
                    user_location=[request.user_latitude, request.user_longitude],
                    processing_time_seconds=round(processing_time, 2)
                )
            
            # Mobile app search - use fallback to show nearest facilities
            logger.info("No facilities with specific antivenom found. Fetching nearest facilities as fallback...")
            
            try:
                # Get all facilities to show as fallback
                all_facilities = await db_manager.get_all_facilities()
                
                if not all_facilities:
                    processing_time = time.time() - start_time
                    return AntivenomFinderResponse(
                        success=True,
                        message="No facilities found in the system",
                        search_criteria={
                            "snake_id": snake_id,
                            "snake_common_name": request.snake_common_name,
                            "antivenom_type": request.antivenom_type,
                            "user_location": [request.user_latitude, request.user_longitude],
                            "max_distance_km": request.max_distance_km
                        },
                        facilities_found=0,
                        facilities=[],
                        search_radius_km=request.max_distance_km,
                        user_location=[request.user_latitude, request.user_longitude],
                        processing_time_seconds=round(processing_time, 2)
                    )
                
                # Calculate distances to all facilities
                osrm_client = get_osrm_client()
                fallback_facilities = []
                
                for facility in all_facilities:
                    try:
                        if not facility.get("latitude") or not facility.get("longitude"):
                            continue
                        
                        route_info = await osrm_client.get_route_with_fallback(
                            request.user_latitude,
                            request.user_longitude,
                            facility["latitude"],
                            facility["longitude"]
                        )
                        
                        # Create facility info without antivenom data
                        facility_info = FacilityInfo(
                            facility_id=facility["facility_id"],
                            facility_name=facility["facility_name"],
                            facility_type=facility.get("facility_type"),
                            region=facility.get("region"),
                            province=facility.get("province"),
                            city_municipality=facility.get("city_municipality"),
                            address=facility.get("address"),
                            latitude=facility.get("latitude"),
                            longitude=facility.get("longitude"),
                            contact_number=facility.get("contact_number"),
                            facility_email=facility.get("facility_email"),
                            image_url=facility.get("image_url"),
                            antivenoms=[],  # No antivenom for this snake
                            route_info=RouteInfo(**route_info) if route_info.get("success") else None
                        )
                        
                        fallback_facilities.append({
                            "facility": facility_info,
                            "distance_km": route_info.get("distance_km", float('inf'))
                        })
                    except Exception as e:
                        logger.error(f"Error processing fallback facility: {e}")
                        continue
                
                # Sort by distance and get top 5 nearest
                fallback_facilities.sort(key=lambda x: x["distance_km"])
                nearest_facilities = [item["facility"] for item in fallback_facilities[:5]]
                
                processing_time = time.time() - start_time
                
                return AntivenomFinderResponse(
                    success=True,
                    message=f"No facilities with specific antivenom found. Showing {len(nearest_facilities)} nearest facilities. Please contact them for alternative treatment options.",
                    search_criteria={
                        "snake_id": snake_id,
                        "snake_common_name": request.snake_common_name,
                        "antivenom_type": request.antivenom_type,
                        "user_location": [request.user_latitude, request.user_longitude],
                        "max_distance_km": request.max_distance_km
                    },
                    facilities_found=len(nearest_facilities),
                    facilities=nearest_facilities,
                    search_radius_km=request.max_distance_km,
                    user_location=[request.user_latitude, request.user_longitude],
                    processing_time_seconds=round(processing_time, 2)
                )
                
            except Exception as e:
                logger.error(f"Error fetching fallback facilities: {e}")
                processing_time = time.time() - start_time
                return AntivenomFinderResponse(
                    success=True,
                    message="No facilities found with antivenom for this snake species",
                    search_criteria={
                        "snake_id": snake_id,
                        "snake_common_name": request.snake_common_name,
                        "antivenom_type": request.antivenom_type,
                        "user_location": [request.user_latitude, request.user_longitude],
                        "max_distance_km": request.max_distance_km
                    },
                    facilities_found=0,
                    facilities=[],
                    search_radius_km=request.max_distance_km,
                    user_location=[request.user_latitude, request.user_longitude],
                    processing_time_seconds=round(processing_time, 2)
                )
        
        # Step 3: Calculate distances and prepare facility info
        logger.info(f"Calculating distances for {len(facilities_data)} facilities")
        
        facilities_with_distance = []
        osrm_client = get_osrm_client()
        
        # Process facilities and calculate distances
        for facility_data in facilities_data:
            try:
                # Skip facilities without coordinates
                if not facility_data.get("latitude") or not facility_data.get("longitude"):
                    logger.warning(f"Facility {facility_data.get('facility_name')} has no coordinates")
                    continue
                
                # Calculate route info
                route_info = await osrm_client.get_route_with_fallback(
                    request.user_latitude,
                    request.user_longitude,
                    facility_data["latitude"],
                    facility_data["longitude"]
                )
                
                # Filter by max distance if specified
                if (request.max_distance_km and 
                    route_info.get("distance_km") and 
                    route_info["distance_km"] > request.max_distance_km):
                    continue
                
                # Create antivenom info
                antivenom_info = AntivenomInfo(
                    antivenom_id=facility_data["antivenom_id"],
                    antivenom_name=facility_data["antivenom_name"],
                    manufacturer=facility_data.get("manufacturer"),
                    quantity=facility_data["quantity"],
                    expiration_date=facility_data.get("expiration_date"),
                    batch_no=facility_data.get("batch_no")
                )
                
                # Create facility info
                facility_info = FacilityInfo(
                    facility_id=facility_data["facility_id"],
                    facility_name=facility_data["facility_name"],
                    facility_type=facility_data["facility_type"],
                    region=facility_data["region"],
                    province=facility_data["province"],
                    city_municipality=facility_data["city_municipality"],
                    address=facility_data.get("address"),
                    latitude=facility_data.get("latitude"),
                    longitude=facility_data.get("longitude"),
                    contact_number=facility_data.get("contact_number"),
                    facility_email=facility_data.get("facility_email"),
                    image_url=facility_data.get("image_url"),
                    antivenoms=[antivenom_info],
                    route_info=RouteInfo(**route_info) if route_info.get("success") else None
                )
                
                facilities_with_distance.append({
                    "facility": facility_info,
                    "distance_km": route_info.get("distance_km", float('inf'))
                })
                
            except Exception as e:
                logger.error(f"Error processing facility {facility_data.get('facility_name')}: {e}")
                continue
        
        # Step 4: Sort by distance and prepare response
        facilities_with_distance.sort(key=lambda x: x["distance_km"])
        
        # Extract just the facility objects
        sorted_facilities = [item["facility"] for item in facilities_with_distance]
        
        processing_time = time.time() - start_time
        
        # Determine search criteria for response
        search_criteria = {
            "snake_id": snake_id,
            "snake_common_name": request.snake_common_name,
            "antivenom_type": request.antivenom_type,
            "user_location": [request.user_latitude, request.user_longitude],
            "max_distance_km": request.max_distance_km
        }
        
        # Create success message
        if sorted_facilities:
            nearest_distance = facilities_with_distance[0]["distance_km"] if facilities_with_distance else None
            message = f"Found {len(sorted_facilities)} facilities with antivenom"
            if nearest_distance is not None:
                message += f" (nearest: {nearest_distance:.1f}km)"
        else:
            message = "No facilities found within specified distance"
        
        return AntivenomFinderResponse(
            success=True,
            message=message,
            search_criteria=search_criteria,
            facilities_found=len(sorted_facilities),
            facilities=sorted_facilities,
            search_radius_km=request.max_distance_km,
            user_location=[request.user_latitude, request.user_longitude],
            processing_time_seconds=round(processing_time, 2)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in antivenom finder: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while finding antivenom facilities"
        )


@router.post(
    "/antivenom/facilities",
    response_model=FacilityListResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse}
    },
    summary="Get facilities with specific antivenom",
    description="""
    Get healthcare facilities that stock a specific antivenom product.
    Useful for staff to find facilities with particular antivenom types.
    
    The process:
    1. Search for facilities with specified antivenom or snake-specific antivenom
    2. Calculate distance and travel time to each facility
    3. Return detailed facility information including stock details
    """
)
async def get_facilities_with_antivenom(request: FacilityListRequest):
    """
    Get facilities that stock specific antivenom
    
    Args:
        request: FacilityListRequest with search criteria
        
    Returns:
        FacilityListResponse with facility list
    """
    start_time = time.time()
    
    try:
        # Validate input
        if not request.antivenom_name and not request.snake_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either antivenom_name or snake_id must be provided"
            )
        
        # Step 1: Find facilities based on search criteria
        facilities_data = []
        
        if request.antivenom_name:
            # Search by antivenom name
            try:
                facilities_data = await db_manager.get_facilities_with_antivenom_by_name(request.antivenom_name)
            except Exception as e:
                logger.error(f"Error finding facilities by antivenom name: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to find facilities by antivenom name"
                )
        
        elif request.snake_id:
            # Search by snake ID
            try:
                facilities_data = await db_manager.get_facilities_with_antivenom(request.snake_id)
            except Exception as e:
                logger.error(f"Error finding facilities by snake ID: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to find facilities by snake ID"
                )
        
        if not facilities_data:
            processing_time = time.time() - start_time
            return FacilityListResponse(
                success=True,
                message="No facilities found matching the criteria",
                search_criteria={
                    "antivenom_name": request.antivenom_name,
                    "snake_id": request.snake_id,
                    "user_location": [request.user_latitude, request.user_longitude],
                    "max_distance_km": request.max_distance_km
                },
                facilities_found=0,
                facilities=[],
                search_radius_km=request.max_distance_km,
                user_location=[request.user_latitude, request.user_longitude],
                processing_time_seconds=round(processing_time, 2)
            )
        
        # Step 2: Group facilities and calculate distances
        logger.info(f"Processing {len(facilities_data)} facility records")
        
        # Group by facility_id to handle multiple antivenoms per facility
        facility_groups = {}
        for facility_data in facilities_data:
            facility_id = facility_data["facility_id"]
            
            if facility_id not in facility_groups:
                facility_groups[facility_id] = {
                    "facility_data": facility_data,
                    "antivenoms": []
                }
            
            # Add antivenom info
            antivenom_info = AntivenomInfo(
                antivenom_id=facility_data["antivenom_id"],
                antivenom_name=facility_data["antivenom_name"],
                manufacturer=facility_data.get("manufacturer"),
                quantity=facility_data["quantity"],
                expiration_date=facility_data.get("expiration_date"),
                batch_no=facility_data.get("batch_no"),
                target_snakes=facility_data.get("target_snakes", [])
            )
            
            facility_groups[facility_id]["antivenoms"].append(antivenom_info)
        
        # Step 3: Calculate distances for each facility
        facilities_with_distance = []
        osrm_client = get_osrm_client()
        
        for facility_id, group_data in facility_groups.items():
            try:
                facility_data = group_data["facility_data"]
                
                # Skip facilities without coordinates
                if not facility_data.get("latitude") or not facility_data.get("longitude"):
                    logger.warning(f"Facility {facility_data.get('facility_name')} has no coordinates")
                    continue
                
                # Calculate route info
                route_info = await osrm_client.get_route_with_fallback(
                    request.user_latitude,
                    request.user_longitude,
                    facility_data["latitude"],
                    facility_data["longitude"]
                )
                
                # Filter by max distance if specified
                if (request.max_distance_km and 
                    route_info.get("distance_km") and 
                    route_info["distance_km"] > request.max_distance_km):
                    continue
                
                # Create facility info
                facility_info = FacilityInfo(
                    facility_id=facility_data["facility_id"],
                    facility_name=facility_data["facility_name"],
                    facility_type=facility_data["facility_type"],
                    region=facility_data["region"],
                    province=facility_data["province"],
                    city_municipality=facility_data["city_municipality"],
                    address=facility_data.get("address"),
                    latitude=facility_data.get("latitude"),
                    longitude=facility_data.get("longitude"),
                    contact_number=facility_data.get("contact_number"),
                    facility_email=facility_data.get("facility_email"),
                    image_url=facility_data.get("image_url"),
                    antivenoms=group_data["antivenoms"],
                    route_info=RouteInfo(**route_info) if route_info.get("success") else None
                )
                
                facilities_with_distance.append({
                    "facility": facility_info,
                    "distance_km": route_info.get("distance_km", float('inf'))
                })
                
            except Exception as e:
                logger.error(f"Error processing facility {facility_data.get('facility_name')}: {e}")
                continue
        
        # Step 4: Sort by distance and prepare response
        facilities_with_distance.sort(key=lambda x: x["distance_km"])
        
        # Extract facility objects
        sorted_facilities = [item["facility"] for item in facilities_with_distance]
        
        processing_time = time.time() - start_time
        
        # Search criteria for response
        search_criteria = {
            "antivenom_name": request.antivenom_name,
            "snake_id": request.snake_id,
            "user_location": [request.user_latitude, request.user_longitude],
            "max_distance_km": request.max_distance_km
        }
        
        # Create success message
        if sorted_facilities:
            nearest_distance = facilities_with_distance[0]["distance_km"] if facilities_with_distance else None
            message = f"Found {len(sorted_facilities)} facilities"
            if nearest_distance is not None:
                message += f" (nearest: {nearest_distance:.1f}km)"
        else:
            message = "No facilities found within specified distance"
        
        return FacilityListResponse(
            success=True,
            message=message,
            search_criteria=search_criteria,
            facilities_found=len(sorted_facilities),
            facilities=sorted_facilities,
            search_radius_km=request.max_distance_km,
            user_location=[request.user_latitude, request.user_longitude],
            processing_time_seconds=round(processing_time, 2)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in facility listing: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while listing facilities"
        )


@router.get(
    "/antivenom/test-route",
    summary="Test route calculation",
    description="Test OSRM route calculation between two points"
)
async def test_route_calculation(
    start_lat: float = Query(..., description="Starting latitude"),
    start_lon: float = Query(..., description="Starting longitude"),
    end_lat: float = Query(..., description="Destination latitude"),
    end_lon: float = Query(..., description="Destination longitude")
):
    """Test route calculation functionality"""
    try:
        osrm_client = get_osrm_client()
        
        route_info = await osrm_client.get_route_with_fallback(
            start_lat, start_lon, end_lat, end_lon
        )
        
        return {
            "success": True,
            "route_info": route_info,
            "osrm_base_url": osrm_client.base_url
        }
        
    except Exception as e:
        logger.error(f"Error testing route calculation: {e}")
        return {
            "success": False,
            "error": str(e)
        }