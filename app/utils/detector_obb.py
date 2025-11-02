"""
Snake detection utility using YOLOv8s-obb for oriented bounding box detection.
This implementation matches the working web app pipeline with perspective transformation.
"""

import logging
import os
import cv2
import numpy as np
import time
from typing import Dict, Any, List, Tuple
from ultralytics import YOLO
import torch

from app.utils.config import settings

logger = logging.getLogger(__name__)


class SnakeDetectorOBB:
    """Snake detection using YOLOv8-obb with perspective transformation"""
    
    def __init__(self):
        self.model = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self._load_model()
    
    def _load_model(self):
        """Load the YOLOv8-obb detection model"""
        try:
            model_path = settings.detection_model_path
            if not os.path.exists(model_path):
                logger.error(f"Detection model not found at {model_path}")
                raise FileNotFoundError(f"Detection model not found at {model_path}")
            
            self.model = YOLO(model_path)
            self.model.to(self.device)
            logger.info(f"Detection model loaded successfully from {model_path} on {self.device}")
            
        except Exception as e:
            logger.error(f"Failed to load detection model: {e}")
            raise
    
    def detect_and_crop(self, image_path: str, confidence_threshold: float = 0.3) -> Dict[str, Any]:
        """
        Detect snake using OBB and create perspective-corrected crops.
        This matches the working pipeline from your web app.
        
        Args:
            image_path: Path to the input image
            confidence_threshold: Minimum confidence score for detection
            
        Returns:
            Dict containing detection results with OBB-cropped images
        """
        try:
            if not os.path.exists(image_path):
                return {
                    "success": False,
                    "error": "Image file not found",
                    "detections": []
                }
            
            # Read image with OpenCV
            img = cv2.imread(image_path)
            if img is None:
                return {
                    "success": False,
                    "error": "Failed to read image",
                    "detections": []
                }
            
            # Run YOLOv8-obb prediction with confidence threshold
            logger.info(f"Running detection with confidence threshold: {confidence_threshold}")
            results = self.model.predict(image_path, conf=confidence_threshold)[0]
            
            detections = []
            
            # Check if OBB (Oriented Bounding Box) results exist
            if results.obb is not None and len(results.obb.xyxyxyxy) > 0:
                logger.info(f"Found {len(results.obb.xyxyxyxy)} OBB detections")
                
                for i, obb_pts in enumerate(results.obb.xyxyxyxy.cpu().numpy()):
                    # Get the 4 corner points of the oriented bounding box
                    points = np.array(obb_pts, dtype=np.float32).reshape((4, 2))
                    
                    # Calculate width and height of the rotated box
                    width = int(np.linalg.norm(points[0] - points[1]))
                    height = int(np.linalg.norm(points[1] - points[2]))
                    
                    # Define destination points for perspective transform (straight rectangle)
                    dst_pts = np.array([
                        [0, 0],
                        [width - 1, 0],
                        [width - 1, height - 1],
                        [0, height - 1]
                    ], dtype=np.float32)
                    
                    # Get perspective transformation matrix
                    M = cv2.getPerspectiveTransform(points, dst_pts)
                    
                    # Apply perspective warp to straighten the rotated detection
                    warped = cv2.warpPerspective(img, M, (width, height))
                    
                    # Save the cropped/warped image
                    timestamp = int(time.time() * 1000)
                    crop_filename = f"crop_{i}_{timestamp}.jpg"
                    crop_path = os.path.join("temp", crop_filename)
                    
                    # Ensure temp directory exists
                    os.makedirs("temp", exist_ok=True)
                    cv2.imwrite(crop_path, warped)
                    
                    # Get confidence score (but don't filter by it - pass all OBB detections)
                    confidence = float(results.obb.conf[i].cpu().numpy())
                    
                    # Calculate regular bbox from OBB points for compatibility
                    x_coords = points[:, 0]
                    y_coords = points[:, 1]
                    x1, y1 = int(x_coords.min()), int(y_coords.min())
                    x2, y2 = int(x_coords.max()), int(y_coords.max())
                    
                    detection = {
                        "bbox": [x1, y1, x2, y2],
                        "obb_points": points.tolist(),  # Keep OBB points for visualization
                        "confidence": confidence,
                        "class_id": 0,
                        "class_name": "snake",
                        "cropped_image_path": crop_path,
                        "crop_size": (width, height)
                    }
                    detections.append(detection)
                    
                    logger.info(f"Snake detected: confidence={confidence:.3f}, crop_size=({width}x{height})")
            
            success = len(detections) > 0
            message = f"Found {len(detections)} snake(s)" if success else "No snake detected"
            
            return {
                "success": success,
                "detections": detections,
                "message": message
            }
            
        except Exception as e:
            logger.error(f"Detection error: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e),
                "detections": []
            }


# Global detector instance
_detector = None

def get_detector_obb() -> SnakeDetectorOBB:
    """Get or create global detector instance"""
    global _detector
    if _detector is None:
        _detector = SnakeDetectorOBB()
    return _detector


def cleanup_temp_files():
    """Clean up temporary cropped images"""
    try:
        temp_dir = "temp"
        if os.path.exists(temp_dir):
            for file in os.listdir(temp_dir):
                if file.startswith("crop_") and file.endswith(".jpg"):
                    try:
                        os.remove(os.path.join(temp_dir, file))
                    except:
                        pass
    except Exception as e:
        logger.warning(f"Failed to cleanup temp files: {e}")