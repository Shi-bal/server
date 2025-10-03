"""
OSRM (Open Source Routing Machine) integration for distance and route calculation.
Handles routing queries for facility distance calculations.
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional, Tuple
import httpx
from app.utils.config import settings

logger = logging.getLogger(__name__)


class OSRMClient:
    """OSRM API client for routing and distance calculations"""
    
    def __init__(self):
        self.base_url = settings.osrm_base_url
        self.timeout = 30.0
    
    async def get_route_info(
        self, 
        start_lat: float, 
        start_lon: float, 
        end_lat: float, 
        end_lon: float
    ) -> Dict[str, Any]:
        """
        Get route information between two points
        
        Args:
            start_lat: Starting latitude
            start_lon: Starting longitude
            end_lat: Destination latitude
            end_lon: Destination longitude
            
        Returns:
            Route information including distance and duration
        """
        try:
            # Construct OSRM route URL
            url = f"{self.base_url}/route/v1/driving/{start_lon},{start_lat};{end_lon},{end_lat}"
            params = {
                "overview": "false",  # Don't need full geometry
                "alternatives": "false",
                "steps": "false",
                "geometries": "geojson"
            }
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                
                data = response.json()
                
                if data.get("code") != "Ok":
                    raise ValueError(f"OSRM API error: {data.get('message', 'Unknown error')}")
                
                routes = data.get("routes", [])
                if not routes:
                    raise ValueError("No routes found")
                
                route = routes[0]  # Take the first route
                
                # Extract route information
                distance_meters = route.get("distance", 0)
                duration_seconds = route.get("duration", 0)
                
                return {
                    "success": True,
                    "distance_meters": distance_meters,
                    "distance_km": round(distance_meters / 1000, 2),
                    "duration_seconds": duration_seconds,
                    "duration_minutes": round(duration_seconds / 60, 1),
                    "duration_hours": round(duration_seconds / 3600, 2),
                    "formatted_duration": self._format_duration(duration_seconds),
                    "start_coordinates": [start_lat, start_lon],
                    "end_coordinates": [end_lat, end_lon]
                }
                
        except httpx.TimeoutException:
            logger.error("OSRM request timeout")
            return {
                "success": False,
                "error": "Routing service timeout",
                "distance_meters": None,
                "distance_km": None,
                "duration_seconds": None,
                "duration_minutes": None
            }
        except httpx.HTTPStatusError as e:
            logger.error(f"OSRM HTTP error: {e.response.status_code}")
            return {
                "success": False,
                "error": f"Routing service error: {e.response.status_code}",
                "distance_meters": None,
                "distance_km": None,
                "duration_seconds": None,
                "duration_minutes": None
            }
        except Exception as e:
            logger.error(f"OSRM request error: {e}")
            return {
                "success": False,
                "error": str(e),
                "distance_meters": None,
                "distance_km": None,
                "duration_seconds": None,
                "duration_minutes": None
            }
    
    async def get_distance_matrix(
        self, 
        sources: List[Tuple[float, float]], 
        destinations: List[Tuple[float, float]]
    ) -> Dict[str, Any]:
        """
        Get distance matrix between multiple points
        
        Args:
            sources: List of (lat, lon) tuples for source points
            destinations: List of (lat, lon) tuples for destination points
            
        Returns:
            Distance matrix with durations and distances
        """
        try:
            # Convert coordinates to OSRM format (lon,lat)
            source_coords = ";".join([f"{lon},{lat}" for lat, lon in sources])
            dest_coords = ";".join([f"{lon},{lat}" for lat, lon in destinations])
            
            # If sources and destinations are the same, we only need one coordinate string
            if sources == destinations:
                coords = source_coords
                url = f"{self.base_url}/table/v1/driving/{coords}"
            else:
                coords = f"{source_coords};{dest_coords}"
                source_indices = list(range(len(sources)))
                dest_indices = list(range(len(sources), len(sources) + len(destinations)))
                url = f"{self.base_url}/table/v1/driving/{coords}"
                url += f"?sources={';'.join(map(str, source_indices))}"
                url += f"&destinations={';'.join(map(str, dest_indices))}"
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                
                data = response.json()
                
                if data.get("code") != "Ok":
                    raise ValueError(f"OSRM API error: {data.get('message', 'Unknown error')}")
                
                return {
                    "success": True,
                    "durations": data.get("durations", []),
                    "distances": data.get("distances", []),
                    "sources": sources,
                    "destinations": destinations
                }
                
        except Exception as e:
            logger.error(f"OSRM distance matrix error: {e}")
            return {
                "success": False,
                "error": str(e),
                "durations": [],
                "distances": []
            }
    
    def _format_duration(self, duration_seconds: float) -> str:
        """
        Format duration in a human-readable way
        
        Args:
            duration_seconds: Duration in seconds
            
        Returns:
            Formatted duration string
        """
        try:
            if duration_seconds < 60:
                return f"{int(duration_seconds)}s"
            elif duration_seconds < 3600:
                minutes = int(duration_seconds / 60)
                seconds = int(duration_seconds % 60)
                return f"{minutes}m {seconds}s" if seconds > 0 else f"{minutes}m"
            else:
                hours = int(duration_seconds / 3600)
                minutes = int((duration_seconds % 3600) / 60)
                return f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"
        except:
            return "N/A"
    
    def calculate_straight_line_distance(
        self, 
        lat1: float, 
        lon1: float, 
        lat2: float, 
        lon2: float
    ) -> float:
        """
        Calculate straight-line distance between two points using Haversine formula
        Used as fallback when OSRM is unavailable
        
        Args:
            lat1, lon1: First point coordinates
            lat2, lon2: Second point coordinates
            
        Returns:
            Distance in kilometers
        """
        import math
        
        # Convert latitude and longitude from degrees to radians
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        
        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        # Radius of earth in kilometers
        r = 6371
        
        return c * r
    
    async def get_route_with_fallback(
        self, 
        start_lat: float, 
        start_lon: float, 
        end_lat: float, 
        end_lon: float
    ) -> Dict[str, Any]:
        """
        Get route information with fallback to straight-line distance
        
        Args:
            start_lat: Starting latitude
            start_lon: Starting longitude
            end_lat: Destination latitude
            end_lon: Destination longitude
            
        Returns:
            Route information with fallback calculation
        """
        # Try OSRM first
        route_info = await self.get_route_info(start_lat, start_lon, end_lat, end_lon)
        
        if route_info.get("success", False):
            return route_info
        
        # Fallback to straight-line distance
        try:
            straight_distance = self.calculate_straight_line_distance(
                start_lat, start_lon, end_lat, end_lon
            )
            
            # Estimate driving time (assuming average speed of 50 km/h)
            estimated_duration_hours = straight_distance / 50
            estimated_duration_seconds = estimated_duration_hours * 3600
            
            return {
                "success": True,
                "fallback": True,
                "distance_meters": straight_distance * 1000,
                "distance_km": round(straight_distance, 2),
                "duration_seconds": estimated_duration_seconds,
                "duration_minutes": round(estimated_duration_seconds / 60, 1),
                "duration_hours": round(estimated_duration_hours, 2),
                "formatted_duration": self._format_duration(estimated_duration_seconds),
                "start_coordinates": [start_lat, start_lon],
                "end_coordinates": [end_lat, end_lon],
                "note": "Estimated based on straight-line distance (routing service unavailable)"
            }
            
        except Exception as e:
            logger.error(f"Fallback distance calculation failed: {e}")
            return {
                "success": False,
                "error": "Unable to calculate distance",
                "distance_meters": None,
                "distance_km": None,
                "duration_seconds": None,
                "duration_minutes": None
            }


# Global OSRM client instance
osrm_client = None


def get_osrm_client() -> OSRMClient:
    """Get or create the global OSRM client instance"""
    global osrm_client
    if osrm_client is None:
        osrm_client = OSRMClient()
    return osrm_client