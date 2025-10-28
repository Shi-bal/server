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
    
    
    def classify_with_confidence_analysis(self, image_path: str, top_k: int = 5) -> Dict[str, Any]:
        """
        Classify snake species with detailed confidence analysis for top-k predictions.
        This is the method called by the snake_id endpoint.
        
        Args:
            image_path: Path to the image to classify
            top_k: Number of top predictions to return
            
        Returns:
            Dict with success status, predictions array, and best_prediction
        """
        try:
            if not os.path.exists(image_path):
                return {
                    "success": False,
                    "error": "Image not found",
                    "predictions": [],
                    "best_prediction": None
                }
            
            # Run classification
            cls_results = self.model.predict(image_path)[0]
            
            # Check if probs exist (classification results)
            if cls_results.probs is None:
                return {
                    "success": False,
                    "error": "No classification probabilities returned",
                    "predictions": [],
                    "best_prediction": None
                }
            
            # Get top-k predictions
            probs_data = cls_results.probs.data.cpu().numpy()
            top_indices = probs_data.argsort()[-top_k:][::-1]  # Get top k indices, highest first
            
            predictions = []
            for rank, idx in enumerate(top_indices, start=1):
                class_name = self.model.names[int(idx)]
                confidence = float(probs_data[idx])
                
                # Format class name: replace underscores/dashes with spaces and title case
                pretty_name = class_name.replace("_", " ").replace("-", " ").title()
                
                predictions.append({
                    "rank": rank,
                    "class_name": pretty_name,
                    "scientific_name": pretty_name,  # Use same as class_name (will be updated by DB lookup)
                    "raw_class_name": class_name,
                    "confidence": confidence,
                    "confidence_percentage": confidence * 100,
                    "class_id": int(idx)
                })
            
            # Best prediction is the first one (highest confidence)
                best_prediction = predictions[0] if predictions else None
            
                # Enforce 90% confidence threshold
                threshold = 0.9
                if best_prediction and best_prediction["confidence"] < threshold:
                    # Label as unknown if below threshold
                    best_prediction = {
                        "rank": 1,
                        "class_name": "Unknown",
                        "scientific_name": "Unknown",
                        "raw_class_name": "Unknown",
                        "confidence": best_prediction["confidence"],
                        "confidence_percentage": best_prediction["confidence"] * 100,
                        "class_id": None
                    }
                    logger.info(f"Classification below threshold: labeled as Unknown (confidence={best_prediction['confidence']:.3f})")
                elif best_prediction:
                    logger.info(f"Classification complete: {best_prediction['class_name']} "
                               f"(confidence={best_prediction['confidence']:.3f})")
                else:
                    logger.info("Classification complete: No predictions")

                return {
                    "success": True,
                    "predictions": predictions,
                    "best_prediction": best_prediction
                }
            # Log the result
            if best_prediction:
                logger.info(f"Classification complete: {best_prediction['class_name']} "
                           f"(confidence={best_prediction['confidence']:.3f})")
            else:
                logger.info("Classification complete: No predictions")
            
            return {
                "success": True,
                "predictions": predictions,
                "best_prediction": best_prediction
            }
            
        except Exception as e:
            logger.error(f"Classification error: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e),
                "predictions": [],
                "best_prediction": None
            }
    
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
    
    def get_model_info(self) -> Dict[str, Any]:
        """
        Get information about the classification model.
        
        Returns:
            Dict containing model information
        """
        return {
            "model_type": "YOLOv8s Classification",
            "model_path": settings.classification_model_path,
            "device": self.device,
            "num_classes": len(self.class_names),
            "task": "Snake Species Classification using probs.top1"
        }


# Global classifier instance
_classifier = None

def get_classifier() -> SnakeClassifier:
    """Get or create global classifier instance"""
    global _classifier
    if _classifier is None:
        _classifier = SnakeClassifier()
    return _classifier