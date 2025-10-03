"""
Image processing utilities for VenomX.
Handles image validation, preprocessing, and format conversion.
"""

import logging
import os
import tempfile
from typing import Tuple, Optional, Dict, Any
from PIL import Image, ImageOps
import cv2
import numpy as np
from io import BytesIO

logger = logging.getLogger(__name__)


class ImageProcessor:
    """Image processing utilities for snake identification."""
    
    # Supported image formats
    SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp'}
    
    # Maximum image dimensions
    MAX_WIDTH = 2048
    MAX_HEIGHT = 2048
    
    # Maximum file size (10MB)
    MAX_FILE_SIZE = 10 * 1024 * 1024
    
    @staticmethod
    def validate_image(image_data: bytes, filename: str) -> Dict[str, Any]:
        """
        Validate uploaded image data.
        
        Args:
            image_data: Raw image data bytes
            filename: Original filename
            
        Returns:
            Dict with validation results
        """
        result = {
            'valid': False,
            'error': None,
            'warnings': [],
            'format': None,
            'size': None,
            'dimensions': None
        }
        
        try:
            # Check file size
            if len(image_data) > ImageProcessor.MAX_FILE_SIZE:
                result['error'] = f"File too large: {len(image_data)} bytes (max: {ImageProcessor.MAX_FILE_SIZE})"
                return result
            
            # Check file extension
            file_ext = os.path.splitext(filename)[1].lower()
            if file_ext not in ImageProcessor.SUPPORTED_FORMATS:
                result['error'] = f"Unsupported format: {file_ext} (supported: {ImageProcessor.SUPPORTED_FORMATS})"
                return result
            
            # Try to open with PIL
            image = Image.open(BytesIO(image_data))
            
            # Verify it's a valid image
            image.verify()
            
            # Re-open for processing (verify() closes the image)
            image = Image.open(BytesIO(image_data))
            
            result['format'] = image.format
            result['size'] = len(image_data)
            result['dimensions'] = image.size
            
            # Check dimensions
            width, height = image.size
            if width > ImageProcessor.MAX_WIDTH or height > ImageProcessor.MAX_HEIGHT:
                result['warnings'].append(f"Large image ({width}x{height}), will be resized")
            
            # Check if image is grayscale
            if image.mode in ('L', 'LA'):
                result['warnings'].append("Grayscale image detected, converting to RGB")
            
            result['valid'] = True
            
        except Exception as e:
            result['error'] = f"Invalid image: {str(e)}"
        
        return result
    
    @staticmethod
    def preprocess_image(image_data: bytes, target_size: Optional[Tuple[int, int]] = None) -> np.ndarray:
        """
        Preprocess image for AI model inference.
        
        Args:
            image_data: Raw image data bytes
            target_size: Optional target size (width, height)
            
        Returns:
            Preprocessed image as numpy array
        """
        try:
            # Load image with PIL
            image = Image.open(BytesIO(image_data))
            
            # Convert to RGB if needed
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Auto-orient image based on EXIF data
            image = ImageOps.exif_transpose(image)
            
            # Resize if needed
            if target_size:
                image = image.resize(target_size, Image.Resampling.LANCZOS)
            elif image.size[0] > ImageProcessor.MAX_WIDTH or image.size[1] > ImageProcessor.MAX_HEIGHT:
                # Maintain aspect ratio while resizing
                image.thumbnail((ImageProcessor.MAX_WIDTH, ImageProcessor.MAX_HEIGHT), Image.Resampling.LANCZOS)
            
            # Convert to numpy array
            image_array = np.array(image)
            
            logger.info(f"Image preprocessed: shape={image_array.shape}")
            return image_array
            
        except Exception as e:
            logger.error(f"Image preprocessing failed: {e}")
            raise
    
    @staticmethod
    def save_temp_image(image_data: bytes, suffix: str = '.jpg') -> str:
        """
        Save image data to a temporary file.
        
        Args:
            image_data: Raw image data bytes
            suffix: File extension for temp file
            
        Returns:
            Path to temporary file
        """
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_file.write(image_data)
                temp_path = temp_file.name
            
            logger.debug(f"Temporary image saved: {temp_path}")
            return temp_path
            
        except Exception as e:
            logger.error(f"Failed to save temporary image: {e}")
            raise
    
    @staticmethod
    def crop_image_region(image_array: np.ndarray, bbox: Tuple[int, int, int, int], 
                         padding: int = 20) -> np.ndarray:
        """
        Crop a region from an image with optional padding.
        
        Args:
            image_array: Input image as numpy array
            bbox: Bounding box as (x1, y1, x2, y2)
            padding: Padding pixels around the bounding box
            
        Returns:
            Cropped image region
        """
        try:
            height, width = image_array.shape[:2]
            x1, y1, x2, y2 = bbox
            
            # Add padding and ensure bounds
            x1 = max(0, x1 - padding)
            y1 = max(0, y1 - padding)
            x2 = min(width, x2 + padding)
            y2 = min(height, y2 + padding)
            
            # Crop the region
            cropped = image_array[y1:y2, x1:x2]
            
            logger.debug(f"Image cropped: bbox=({x1},{y1},{x2},{y2}), shape={cropped.shape}")
            return cropped
            
        except Exception as e:
            logger.error(f"Image cropping failed: {e}")
            raise
    
    @staticmethod
    def enhance_image(image_array: np.ndarray) -> np.ndarray:
        """
        Apply image enhancements for better AI inference.
        
        Args:
            image_array: Input image as numpy array
            
        Returns:
            Enhanced image
        """
        try:
            # Convert to BGR for OpenCV
            if len(image_array.shape) == 3:
                image_bgr = cv2.cvtColor(image_array, cv2.COLOR_RGB2BGR)
            else:
                image_bgr = image_array
            
            # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
            lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            lab[:, :, 0] = clahe.apply(lab[:, :, 0])
            enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
            
            # Convert back to RGB
            if len(image_array.shape) == 3:
                enhanced = cv2.cvtColor(enhanced, cv2.COLOR_BGR2RGB)
            
            logger.debug("Image enhancement applied")
            return enhanced
            
        except Exception as e:
            logger.warning(f"Image enhancement failed, using original: {e}")
            return image_array