"""
Snake classification utility using YOLOv8 for species classification.
This implementation uses probs.top1 for proper classification results.
"""

import logging
import os
import torch
from typing import Dict, Any
from ultralytics import YOLO

from app.utils.config import settings

logger = logging.getLogger(__name__)


class SnakeClassifier:
    """Snake species classification using YOLOv8 classification with probs"""
    
    def __init__(self):
        self.model = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.class_names = {}
        self._load_model()
    
    def _load_model(self):
        """Load the YOLOv8 classification model"""
        try:
            model_path = settings.classification_model_path
            if not os.path.exists(model_path):
                logger.error(f"Classification model not found at {model_path}")
                raise FileNotFoundError(f"Classification model not found at {model_path}")
            
            self.model = YOLO(model_path)
            self.model.to(self.device)
            
            # Get class names from model
            if hasattr(self.model, 'names'):
                self.class_names = self.model.names
                logger.info(f"Classification model loaded with {len(self.class_names)} classes")
            
            logger.info(f"Classification model loaded successfully from {model_path} on {self.device}")
            
        except Exception as e:
            logger.error(f"Failed to load classification model: {e}")
            raise
    
    
    def classify(self, crop_path: str) -> Dict[str, Any]:
        """
        Classify snake species from cropped image.
        Uses probs.top1 and probs.top1conf for proper classification results.
        
        Args:
            crop_path: Path to the cropped snake image
            
        Returns:
            Dict containing classification results
        """
        try:
            if not os.path.exists(crop_path):
                return {
                    "success": False,
                    "error": "Cropped image not found",
                    "predicted_class": None,
                    "confidence": 0.0
                }
            
            # Run classification
            cls_results = self.model.predict(crop_path)[0]
            
            # Check if probs exist (classification results)
            if cls_results.probs is not None:
                # Get top prediction using probs.top1 (like the working code)
                class_id = int(cls_results.probs.top1)
                class_name = self.model.names[class_id]
                confidence = float(cls_results.probs.top1conf)
                
                # Format class name: replace underscores/dashes with spaces and title case
                # This handles both "Common_Mock_Viper" and "Common-Mock-Viper" formats
                pretty_name = class_name.replace("_", " ").replace("-", " ").title()
                
                logger.info(f"Classified as: {pretty_name} (confidence={confidence:.3f})")
                
                return {
                    "success": True,
                    "predicted_class": pretty_name,
                    "raw_class_name": class_name,  # Keep original for debugging
                    "confidence": confidence,
                    "class_id": class_id
                }
            else:
                return {
                    "success": False,
                    "error": "No classification probabilities returned",
                    "predicted_class": None,
                    "confidence": 0.0
                }
                
        except Exception as e:
            logger.error(f"Classification error: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e),
                "predicted_class": None,
                "confidence": 0.0
            }


# Global classifier instance
_classifier = None

def get_classifier() -> SnakeClassifier:
    """Get or create global classifier instance"""
    global _classifier
    if _classifier is None:
        _classifier = SnakeClassifier()
    return _classifier