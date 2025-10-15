"""
Database connection and utility functions for VenomX.
Handles Supabase/PostgreSQL connection and common database operations.
"""

import logging
from typing import Optional, List, Dict, Any
import asyncpg
from supabase import create_client, Client
from app.utils.config import settings

logger = logging.getLogger(__name__)

# Global database pool
db_pool: Optional[asyncpg.Pool] = None
supabase: Optional[Client] = None


async def init_db():
    """Initialize database connections"""
    global db_pool, supabase
    
    try:
        # Initialize Supabase client (bypasses RLS with service role key)
        supabase = create_client(settings.supabase_url, settings.supabase_service_key)
        logger.info("✅ Supabase client initialized successfully with service role key")
        logger.info("   Service role key bypasses RLS policies automatically")
        
        # Note: asyncpg pool not needed - Supabase client handles everything
        # and properly bypasses RLS policies with the service role key
        db_pool = None
        logger.info("   Using Supabase client for all database operations")
            
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")
        raise


async def get_db_connection():
    """Get a database connection from the pool"""
    if supabase is None:
        raise RuntimeError("Supabase client not initialized")
    return await db_pool.acquire()


async def release_db_connection(connection):
    """Release a database connection back to the pool"""
    if db_pool is None:
        raise RuntimeError("Database pool not initialized")
    await db_pool.release(connection)


def get_supabase_client() -> Client:
    """Get Supabase client instance"""
    if supabase is None:
        raise RuntimeError("Supabase client not initialized")
    return supabase


class DatabaseManager:
    """Database operations manager using Supabase client (bypasses RLS with service role key)"""
    
    @staticmethod
    async def get_snake_by_common_name(common_name: str) -> Optional[Dict[str, Any]]:
        """
        Get snake information by common name
        Uses Supabase client with service role key to bypass RLS policies.
        
        Args:
            common_name: Common name of the snake (e.g., "Common Mock Viper")
            
        Returns:
            Snake information dict or None if not found
        """
        try:
            client = get_supabase_client()
            
            # Query using Supabase client (service role key bypasses RLS)
            response = client.table('snakes').select(
                'snake_id, scientific_name, common_name, fang_type, description, danger_level, image_url'
            ).ilike('common_name', common_name).execute()
            
            if response.data and len(response.data) > 0:
                logger.info(f"Found snake by common name: {response.data[0].get('scientific_name')}")
                return response.data[0]
            
            logger.warning(f"No snake found with common name: {common_name}")
            return None
                
        except Exception as e:
            logger.error(f"Error fetching snake by common name: {e}")
            raise
    
    @staticmethod
    async def get_facilities_with_antivenom(snake_id: int) -> List[Dict[str, Any]]:
        """
        Get facilities that have antivenom for a specific snake
        Uses Supabase client with service role key to bypass RLS policies.
        
        Args:
            snake_id: ID of the snake
            
        Returns:
            List of facilities with antivenom stock
        """
        try:
            client = get_supabase_client()
            
            # First, get antivenom IDs that target this snake
            antivenom_targets = client.table('antivenom_snake_targets').select(
                'antivenom_id'
            ).eq('snake_id', snake_id).execute()
            
            if not antivenom_targets.data:
                logger.info(f"No antivenoms found for snake_id: {snake_id}")
                return []
            
            antivenom_ids = [item['antivenom_id'] for item in antivenom_targets.data]
            
            # Get facilities with stock of these antivenoms
            facilities_stock = client.table('facility_antivenom_stock').select(
                '''
                facility_id,
                antivenom_id,
                quantity,
                expiration_date,
                batch_no,
                facilities(
                    facility_id,
                    facility_name,
                    facility_type,
                    region,
                    province,
                    city_municipality,
                    address,
                    latitude,
                    longitude,
                    contact_number,
                    facility_email,
                    is_verified
                ),
                antivenoms(
                    antivenom_id,
                    product_name,
                    manufacturer
                )
                '''
            ).in_('antivenom_id', antivenom_ids).gt('quantity', 0).execute()
            
            # Process and format results
            facilities = []
            for stock in facilities_stock.data:
                if stock.get('facilities'):
                    facility = stock['facilities']
                    antivenom = stock.get('antivenoms', {})
                    
                    # Check expiration date
                    exp_date = stock.get('expiration_date')
                    if exp_date:
                        from datetime import datetime
                        if datetime.fromisoformat(exp_date.replace('Z', '+00:00')).date() <= datetime.now().date():
                            continue
                    
                    facilities.append({
                        'facility_id': facility.get('facility_id'),
                        'facility_name': facility.get('facility_name'),
                        'facility_type': facility.get('facility_type'),
                        'region': facility.get('region'),
                        'province': facility.get('province'),
                        'city_municipality': facility.get('city_municipality'),
                        'address': facility.get('address'),
                        'latitude': facility.get('latitude'),
                        'longitude': facility.get('longitude'),
                        'contact_number': facility.get('contact_number'),
                        'facility_email': facility.get('facility_email'),
                        'antivenom_id': antivenom.get('antivenom_id'),
                        'antivenom_name': antivenom.get('product_name'),
                        'manufacturer': antivenom.get('manufacturer'),
                        'quantity': stock.get('quantity'),
                        'expiration_date': stock.get('expiration_date'),
                        'batch_no': stock.get('batch_no')
                    })
            
            logger.info(f"Found {len(facilities)} facilities with antivenom for snake_id {snake_id}")
            return facilities
                
        except Exception as e:
            logger.error(f"Error fetching facilities with antivenom: {e}")
            # Try fallback with asyncpg if available
            try:
                if db_pool is not None:
                    connection = await get_db_connection()
                    try:
                        query = """
                            SELECT DISTINCT 
                                f.facility_id,
                                f.facility_name,
                                f.facility_type,
                                f.region,
                                f.province,
                                f.city_municipality,
                                f.address,
                                f.latitude,
                                f.longitude,
                                f.contact_number,
                                f.facility_email,
                                a.antivenom_id,
                                a.product_name as antivenom_name,
                                a.manufacturer,
                                fas.quantity,
                                fas.expiration_date,
                                fas.batch_no
                            FROM facilities f
                            JOIN facility_antivenom_stock fas ON f.facility_id = fas.facility_id
                            JOIN antivenoms a ON fas.antivenom_id = a.antivenom_id
                            JOIN antivenom_snake_targets ast ON a.antivenom_id = ast.antivenom_id
                            WHERE ast.snake_id = $1 
                            -- AND f.is_verified = true
                            AND fas.quantity > 0
                            AND (fas.expiration_date IS NULL OR fas.expiration_date > CURRENT_DATE)
                            ORDER BY f.facility_name
                        """
                        results = await connection.fetch(query, snake_id)
                        return [dict(row) for row in results]
                    finally:
                        await release_db_connection(connection)
            except Exception as fallback_error:
                logger.error(f"Fallback query also failed: {fallback_error}")
            
            raise
    
    @staticmethod
    async def get_facilities_by_antivenom_type(antivenom_type: str) -> List[Dict[str, Any]]:
        """
        Get facilities that have antivenoms of a specific type (polyvalent or monovalent).
        Used by staff web app to search and display on map.
        Uses Supabase client with service role key to bypass RLS policies.
        
        Args:
            antivenom_type: Type of antivenom ('polyvalent' or 'monovalent')
            
        Returns:
            List of facilities with the antivenom type and location data
        """
        try:
            client = get_supabase_client()
            
            # Build query with filters - join through antivenom_types table
            query = client.table('facility_antivenom_stock').select(
                '''
                facility_id,
                antivenom_id,
                quantity,
                expiration_date,
                batch_no,
                facilities(
                    facility_id,
                    facility_name,
                    facility_type,
                    region,
                    province,
                    city_municipality,
                    address,
                    latitude,
                    longitude,
                    contact_number,
                    facility_email
                ),
                antivenoms(
                    antivenom_id,
                    product_name,
                    manufacturer,
                    antivenom_types(
                        type_name
                    )
                )
                '''
            )
            
            # Only get facilities with stock
            query = query.gt('quantity', 0)
            
            # Execute query
            response = query.execute()
            
            # Process and filter results
            facilities = []
            for stock in response.data:
                facility = stock.get('facilities')
                if not facility:
                    continue
                
                # Check if antivenom matches the requested type
                antivenom = stock.get('antivenoms', {})
                antivenom_type_data = antivenom.get('antivenom_types', {})
                if antivenom_type_data.get('type_name') != antivenom_type:
                    continue
                
                # Check expiration date
                exp_date = stock.get('expiration_date')
                if exp_date:
                    from datetime import datetime
                    if datetime.fromisoformat(exp_date.replace('Z', '+00:00')).date() <= datetime.now().date():
                        continue
                
                facilities.append({
                    'facility_id': facility.get('facility_id'),
                    'facility_name': facility.get('facility_name'),
                    'facility_type': facility.get('facility_type'),
                    'region': facility.get('region'),
                    'province': facility.get('province'),
                    'city_municipality': facility.get('city_municipality'),
                    'address': facility.get('address'),
                    'latitude': facility.get('latitude'),
                    'longitude': facility.get('longitude'),
                    'contact_number': facility.get('contact_number'),
                    'facility_email': facility.get('facility_email'),
                    'antivenom_id': antivenom.get('antivenom_id'),
                    'antivenom_name': antivenom.get('product_name'),
                    'antivenom_type': antivenom_type,
                    'manufacturer': antivenom.get('manufacturer'),
                    'quantity': stock.get('quantity'),
                    'expiration_date': stock.get('expiration_date'),
                    'batch_no': stock.get('batch_no')
                })
            
            logger.info(f"Found {len(facilities)} facilities with '{antivenom_type}' antivenoms")
            return facilities
                
        except Exception as e:
            logger.error(f"Error fetching facilities by antivenom type: {e}")
            raise
    
    @staticmethod
    async def get_facilities_with_antivenom_by_name(antivenom_name: str) -> List[Dict[str, Any]]:
        """
        Get facilities that have a specific antivenom by name
        
        Args:
            antivenom_name: Name of the antivenom
            
        Returns:
            List of facilities with the antivenom
        """
        try:
            connection = await get_db_connection()
            try:
                query = """
                    SELECT DISTINCT 
                        f.facility_id,
                        f.facility_name,
                        f.facility_type,
                        f.region,
                        f.province,
                        f.city_municipality,
                        f.address,
                        f.latitude,
                        f.longitude,
                        f.contact_number,
                        f.facility_email,
                        a.antivenom_id,
                        a.product_name as antivenom_name,
                        a.manufacturer,
                        fas.quantity,
                        fas.expiration_date,
                        fas.batch_no,
                        ARRAY_AGG(DISTINCT s.scientific_name) as target_snakes
                    FROM facilities f
                    JOIN facility_antivenom_stock fas ON f.facility_id = fas.facility_id
                    JOIN antivenoms a ON fas.antivenom_id = a.antivenom_id
                    JOIN antivenom_snake_targets ast ON a.antivenom_id = ast.antivenom_id
                    JOIN snakes s ON ast.snake_id = s.snake_id
                    WHERE LOWER(a.product_name) ILIKE LOWER($1)
                    -- AND f.is_verified = true
                    AND fas.quantity > 0
                    AND (fas.expiration_date IS NULL OR fas.expiration_date > CURRENT_DATE)
                    GROUP BY f.facility_id, f.facility_name, f.facility_type, f.region, 
                             f.province, f.city_municipality, f.address, f.latitude, 
                             f.longitude, f.contact_number, f.facility_email, 
                             a.antivenom_id, a.product_name, a.manufacturer, 
                             fas.quantity, fas.expiration_date, fas.batch_no
                    ORDER BY f.facility_name
                """
                results = await connection.fetch(query, f"%{antivenom_name}%")
                
                return [dict(row) for row in results]
                
            finally:
                await release_db_connection(connection)
                
        except Exception as e:
            logger.error(f"Error fetching facilities with antivenom by name: {e}")
            raise
    
    @staticmethod
    async def get_all_snakes() -> List[Dict[str, Any]]:
        """
        Get all snakes from the database
        Uses Supabase client with service role key to bypass RLS policies.
        """
        try:
            client = get_supabase_client()
            
            # Query using Supabase client (service role key bypasses RLS)
            response = client.table('snakes').select(
                'snake_id, scientific_name, common_name, fang_type, description, danger_level, image_url'
            ).order('scientific_name').execute()
            
            logger.info(f"Retrieved {len(response.data)} snakes from database")
            return response.data
                
        except Exception as e:
            logger.error(f"Error fetching all snakes: {e}")
            # Try fallback with asyncpg if available
            try:
                if db_pool is not None:
                    connection = await get_db_connection()
                    try:
                        query = """
                            SELECT snake_id, scientific_name, common_name, fang_type, 
                                   description, danger_level, image_url
                            FROM snakes 
                            ORDER BY scientific_name
                        """
                        results = await connection.fetch(query)
                        return [dict(row) for row in results]
                    finally:
                        await release_db_connection(connection)
            except Exception as fallback_error:
                logger.error(f"Fallback query also failed: {fallback_error}")
            
            raise
    
    @staticmethod
    async def get_snakes_with_antivenom() -> List[Dict[str, Any]]:
        """
        Get only snakes that have at least one antivenom linked in antivenom_snake_targets table.
        This is used for the antivenom finder dropdown to only show snakes with available treatment.
        Uses Supabase client with service role key to bypass RLS policies.
        
        Returns:
            List of snake dictionaries that have antivenom available
        """
        try:
            client = get_supabase_client()
            
            # Query snakes that exist in antivenom_snake_targets
            # This means they have at least one antivenom product linked
            response = client.table('snakes').select(
                'snake_id, scientific_name, common_name, fang_type, description, danger_level, image_url'
            ).in_(
                'snake_id',
                # Subquery to get snake_ids that have antivenoms
                client.table('antivenom_snake_targets').select('snake_id').execute().data
            ).order('common_name').execute()
            
            # Alternative approach using join-like query
            # Get all unique snake_ids from antivenom_snake_targets
            targets_response = client.table('antivenom_snake_targets').select('snake_id').execute()
            snake_ids_with_antivenom = list(set([t['snake_id'] for t in targets_response.data]))
            
            # Get snakes with those IDs
            if snake_ids_with_antivenom:
                snakes_response = client.table('snakes').select(
                    'snake_id, scientific_name, common_name, fang_type, description, danger_level, image_url'
                ).in_('snake_id', snake_ids_with_antivenom).order('common_name').execute()
                
                logger.info(f"Retrieved {len(snakes_response.data)} snakes with antivenom from database")
                return snakes_response.data
            else:
                logger.warning("No snakes found with antivenom links")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching snakes with antivenom: {e}")
            raise


# Create a global instance
db_manager = DatabaseManager()