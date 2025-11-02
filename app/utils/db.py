"""
Database connection and utility functions for VenomX.
Handles Supabase/PostgreSQL connection and common database operations.
"""

import logging
from typing import Optional, List, Dict, Any
import asyncpg
import httpx
from supabase import create_client, Client
from app.utils.config import settings

logger = logging.getLogger(__name__)

# Global database pool
db_pool: Optional[asyncpg.Pool] = None
supabase: Optional[Client] = None

# Constants for database queries
SNAKE_FIELDS = 'snake_id, scientific_name, common_name, family, fang_type, length, description, danger_level, rarity, image_url'


async def init_db():
    """Initialize database connections"""
    global db_pool, supabase
    
    try:
        # Create custom httpx client with increased timeouts for SSL handshake and requests
        # Timeout configuration: connect=10s, read=60s, write=60s, pool=60s
        timeout_config = httpx.Timeout(
            timeout=60.0,      # Default timeout for all operations
            connect=10.0,      # Connection timeout (includes SSL handshake)
            read=60.0,         # Read timeout
            write=60.0,        # Write timeout
            pool=60.0          # Pool timeout
        )
        
        # Create httpx client with retry configuration
        http_client = httpx.Client(
            timeout=timeout_config,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            verify=True  # Enable SSL verification
        )
        
        # Initialize Supabase client with custom HTTP client
        supabase = create_client(
            settings.supabase_url, 
            settings.supabase_service_key
        )
        
        # Patch the Supabase client to use our custom HTTP client
        if hasattr(supabase, 'postgrest'):
            supabase.postgrest.session = http_client
        
        logger.info("✅ Supabase client initialized successfully with service role key")
        logger.info("   Service role key bypasses RLS policies automatically")
        logger.info("   HTTP timeout configured: connect=10s, read/write=60s")
        
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
        Includes retry logic for transient network failures.
        
        Args:
            common_name: Common name of the snake (e.g., "Common Mock Viper")
            
        Returns:
            Snake information dict or None if not found
        """
        max_retries = 3
        retry_delay = 1.0  # seconds
        
        for attempt in range(max_retries):
            try:
                client = get_supabase_client()
                
                # Query using Supabase client (service role key bypasses RLS)
                response = client.table('snakes').select(
                    SNAKE_FIELDS
                ).ilike('common_name', common_name).execute()
                
                if response.data and len(response.data) > 0:
                    logger.info(f"Found snake by common name: {response.data[0].get('scientific_name')}")
                    return response.data[0]
                
                logger.warning(f"No snake found with common name: {common_name}")
                return None
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Database query failed (attempt {attempt + 1}/{max_retries}): {e}")
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    import asyncio
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error(f"Error fetching snake by common name after {max_retries} attempts: {e}")
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
            
            # DEBUG: Log antivenom targets
            logger.info(f"DEBUG: antivenom_snake_targets returned {len(antivenom_targets.data)} rows")
            logger.info(f"DEBUG: Raw antivenom_targets data: {antivenom_targets.data}")
            
            if not antivenom_targets.data:
                logger.info(f"No antivenoms found for snake_id: {snake_id}")
                return []
            
            antivenom_ids = [item['antivenom_id'] for item in antivenom_targets.data]
            
            # Get facilities with stock of these antivenoms (without embedded relationships)
            # Note: Using gte(0) temporarily to show all facilities (including 0 stock) for testing
            facilities_stock = client.table('facility_antivenom_stock').select(
                'stock_id, facility_id, antivenom_id, quantity, expiration_date, batch_no'
            ).in_('antivenom_id', antivenom_ids).gte('quantity', 0).execute()
            
            # DEBUG: Log what we got back
            logger.info(f"DEBUG: facility_antivenom_stock returned {len(facilities_stock.data)} rows")
            logger.info(f"DEBUG: Raw facilities_stock data: {facilities_stock.data}")
            
            if not facilities_stock.data:
                logger.info(f"No facilities with stock found for antivenom_ids: {antivenom_ids}")
                return []
            
            # Get unique facility IDs and antivenom IDs
            facility_ids = list(set([stock['facility_id'] for stock in facilities_stock.data]))
            antivenom_ids_in_stock = list(set([stock['antivenom_id'] for stock in facilities_stock.data]))
            
            # Fetch facilities data separately
            facilities_data = client.table('facilities').select(
                'facility_id, facility_name, facility_type, region, province, city_municipality, address, latitude, longitude, contact_number, facility_email, image_url'
            ).in_('facility_id', facility_ids).execute()
            
            # Fetch antivenoms data separately
            antivenoms_data = client.table('antivenoms').select(
                'antivenom_id, product_name, manufacturer'
            ).in_('antivenom_id', antivenom_ids_in_stock).execute()
            
            # Create lookup dictionaries
            facilities_lookup = {f['facility_id']: f for f in facilities_data.data}
            antivenoms_lookup = {a['antivenom_id']: a for a in antivenoms_data.data}
            
            logger.info(f"DEBUG: Fetched {len(facilities_lookup)} facilities and {len(antivenoms_lookup)} antivenoms")
            
            # Process and format results
            facilities = []
            for stock in facilities_stock.data:
                facility = facilities_lookup.get(stock['facility_id'])
                antivenom = antivenoms_lookup.get(stock['antivenom_id'])
                
                if not facility:
                    logger.warning(f"Facility {stock['facility_id']} not found in lookup")
                    continue
                    
                if not antivenom:
                    logger.warning(f"Antivenom {stock['antivenom_id']} not found in lookup")
                    continue
                
                # Check expiration date
                exp_date = stock.get('expiration_date')
                if exp_date:
                    from datetime import datetime
                    if datetime.fromisoformat(exp_date.replace('Z', '+00:00')).date() <= datetime.now().date():
                        logger.info(f"Skipping expired stock: {stock}")
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
                    'image_url': facility.get('image_url'),
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
    async def get_all_facilities() -> List[Dict[str, Any]]:
        """
        Get all facilities in the system (for fallback when no specific antivenom found).
        
        Returns:
            List of all facilities with basic information
        """
        try:
            client = get_supabase_client()
            
            # Get all facilities
            response = client.table('facilities').select(
                'facility_id, facility_name, facility_type, region, province, city_municipality, address, latitude, longitude, contact_number, facility_email, image_url'
            ).execute()
            
            logger.info(f"Retrieved {len(response.data)} facilities from database")
            return response.data
            
        except Exception as e:
            logger.error(f"Error fetching all facilities: {e}", exc_info=True)
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
            
            # Step 1: Get antivenom_type_id for the requested type
            antivenom_types_response = client.table('antivenom_types').select(
                'type_id, type_name'
            ).eq('type_name', antivenom_type).execute()
            
            if not antivenom_types_response.data:
                logger.info(f"No antivenom type found for: {antivenom_type}")
                return []
            
            type_id = antivenom_types_response.data[0]['type_id']
            logger.info(f"DEBUG: Found type_id={type_id} for antivenom_type='{antivenom_type}'")
            
            # Step 2: Get antivenoms with this type
            antivenoms_response = client.table('antivenoms').select(
                'antivenom_id, product_name, manufacturer, type_id'
            ).eq('type_id', type_id).execute()
            
            if not antivenoms_response.data:
                logger.info(f"No antivenoms found for type: {antivenom_type}")
                return []
            
            antivenom_ids = [a['antivenom_id'] for a in antivenoms_response.data]
            logger.info(f"DEBUG: Found {len(antivenom_ids)} antivenoms with type '{antivenom_type}': {antivenom_ids}")
            
            # Step 3: Get facility stock for these antivenoms
            facilities_stock = client.table('facility_antivenom_stock').select(
                'stock_id, facility_id, antivenom_id, quantity, expiration_date, batch_no'
            ).in_('antivenom_id', antivenom_ids).gt('quantity', 0).execute()
            
            logger.info(f"DEBUG: facility_antivenom_stock returned {len(facilities_stock.data)} rows")
            
            if not facilities_stock.data:
                logger.info(f"No facilities with stock found for antivenom type: {antivenom_type}")
                return []
            
            # Step 4: Get unique facility IDs and antivenom IDs
            facility_ids = list({stock['facility_id'] for stock in facilities_stock.data})
            antivenom_ids_in_stock = list({stock['antivenom_id'] for stock in facilities_stock.data})
            
            # Step 5: Fetch facilities data separately
            facilities_data = client.table('facilities').select(
                'facility_id, facility_name, facility_type, region, province, city_municipality, address, latitude, longitude, contact_number, facility_email, image_url'
            ).in_('facility_id', facility_ids).execute()
            
            # Step 6: Fetch antivenoms data separately
            antivenoms_data = client.table('antivenoms').select(
                'antivenom_id, product_name, manufacturer'
            ).in_('antivenom_id', antivenom_ids_in_stock).execute()
            
            # Create lookup dictionaries
            facilities_lookup = {f['facility_id']: f for f in facilities_data.data}
            antivenoms_lookup = {a['antivenom_id']: a for a in antivenoms_data.data}
            
            logger.info(f"DEBUG: Fetched {len(facilities_lookup)} facilities and {len(antivenoms_lookup)} antivenoms")
            
            # Step 7: Process and format results
            facilities = []
            for stock in facilities_stock.data:
                facility = facilities_lookup.get(stock['facility_id'])
                antivenom = antivenoms_lookup.get(stock['antivenom_id'])
                
                if not facility:
                    logger.warning(f"Facility {stock['facility_id']} not found in lookup")
                    continue
                    
                if not antivenom:
                    logger.warning(f"Antivenom {stock['antivenom_id']} not found in lookup")
                    continue
                
                # Check expiration date
                exp_date = stock.get('expiration_date')
                if exp_date:
                    from datetime import datetime
                    if datetime.fromisoformat(exp_date.replace('Z', '+00:00')).date() <= datetime.now().date():
                        logger.info(f"Skipping expired stock: {stock}")
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
                    'image_url': facility.get('image_url'),
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
            logger.error(f"Error fetching facilities by antivenom type: {e}", exc_info=True)
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
                SNAKE_FIELDS
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
                        query = f"""
                            SELECT {SNAKE_FIELDS}
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
            
            # Get all unique snake_ids from antivenom_snake_targets
            targets_response = client.table('antivenom_snake_targets').select('snake_id').execute()
            logger.info(f"DEBUG: antivenom_snake_targets returned {len(targets_response.data)} rows")
            logger.info(f"DEBUG: Raw data: {targets_response.data}")
            
            snake_ids_with_antivenom = list({t['snake_id'] for t in targets_response.data})
            logger.info(f"DEBUG: Unique snake IDs: {snake_ids_with_antivenom}")
            
            # Get snakes with those IDs
            if snake_ids_with_antivenom:
                snakes_response = client.table('snakes').select(
                    SNAKE_FIELDS
                ).in_('snake_id', snake_ids_with_antivenom).order('common_name').execute()
                
                logger.info(f"Retrieved {len(snakes_response.data)} snakes with antivenom from database")
                return snakes_response.data
            else:
                logger.warning("No snakes found with antivenom links in antivenom_snake_targets table")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching snakes with antivenom: {e}", exc_info=True)
            raise
    
    @staticmethod
    async def get_medically_significant_snakes() -> List[Dict[str, Any]]:
        """
        Get all medically significant snakes (extremely venomous and highly venomous).
        This includes ALL dangerous snakes regardless of antivenom availability.
        Used for snake identification to enable fallback to nearest facilities.
        Uses Supabase client with service role key to bypass RLS policies.
        
        Returns:
            List of medically significant snake dictionaries
        """
        try:
            client = get_supabase_client()
            
            # Get snakes with danger_level = 'extremely venomous' or 'highly venomous'
            snakes_response = client.table('snakes').select(
                SNAKE_FIELDS
            ).in_('danger_level', ['extremely venomous', 'highly venomous']).order('common_name').execute()
            
            logger.info(f"Retrieved {len(snakes_response.data)} medically significant snakes from database")
            return snakes_response.data
                
        except Exception as e:
            logger.error(f"Error fetching medically significant snakes: {e}", exc_info=True)
            raise


# Create a global instance
db_manager = DatabaseManager()