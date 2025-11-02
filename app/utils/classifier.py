"""
Snake classification utility using YOLOv8 for species classification.
This implementation uses probs.top1 for proper classification results.
"""

import logging
import os
import torch
import re
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
    
    def _get_confidence_level(self, confidence: float) -> str:
        """
        Categorize confidence level based on confidence score
        
        Args:
            confidence: Confidence score between 0 and 1
            
        Returns:
            String describing confidence level
        """
        if confidence >= 0.90:
            return "Very High"
        elif confidence >= 0.80:
            return "High"
        elif confidence >= 0.65:
            return "Medium"
        elif confidence >= 0.50:
            return "Low"
        else:
            return "Very Low"
    
    
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
            
            # Minimum confidence threshold to include a prediction (filter out 0% or near-0%)
            min_confidence_threshold = 0.01  # 1% - anything below this is ignored
            
            predictions = []
            rank = 0
            for idx in top_indices:
                class_name = self.model.names[int(idx)]
                confidence = float(probs_data[idx])
                
                # Skip predictions with negligible confidence (0.0% or very close)
                if confidence < min_confidence_threshold:
                    logger.debug(f"Skipping prediction with negligible confidence: {class_name} ({confidence:.4f})")
                    continue
                
                # Preserve hyphens, normalize hyphen spacing, replace underscores with spaces, then title case
                # Example: "Dog-Toothed_Cat_Snake" -> "Dog-Toothed Cat Snake"
                s = re.sub(r"\s*-\s*", "-", class_name)
                pretty_name = s.replace("_", " ").strip().title()
                
                # Get confidence level
                confidence_level = self._get_confidence_level(confidence)
                
                predictions.append({
                    "rank": rank,
                    "class_name": pretty_name,
                    "scientific_name": pretty_name,  # Use same as class_name (will be updated by DB lookup)
                    "raw_class_name": class_name,
                    "confidence": confidence,
                    "confidence_percentage": confidence * 100,
                    "confidence_level": confidence_level,
                    "class_id": int(idx)
                })
                rank += 1
            
            removed_count = top_k - len(predictions)
            min_conf_percent = min_confidence_threshold * 100
            if removed_count > 0:
                logger.info(f"Filtered predictions: {len(predictions)} out of {top_k} (removed {removed_count} with confidence below {min_conf_percent:.0f}%)")
            
            # Best prediction is the first one (highest confidence)
            best_prediction = predictions[0].copy() if predictions else None
            
            # Enforce 90% confidence threshold
            threshold = 0.9
            if best_prediction and best_prediction["confidence"] < threshold:
                # Label as unknown if below threshold
                original_confidence = best_prediction["confidence"]
                original_name = best_prediction["class_name"]
                
                best_prediction = {
                    "rank": 0,
                    "class_name": "Unknown Snake",
                    "scientific_name": "Unknown",
                    "raw_class_name": "Unknown",
                    "confidence": original_confidence,
                    "confidence_percentage": original_confidence * 100,
                    "confidence_level": self._get_confidence_level(original_confidence),
                    "class_id": None,
                    "image_url": None
                }
                logger.info(f"Classification below threshold ({threshold*100}%): {original_name} "
                           f"(confidence={original_confidence:.3f}) → labeled as Unknown Snake")
            elif best_prediction:
                logger.info(f"Classification complete: {best_prediction['class_name']} "
                           f"(confidence={best_prediction['confidence']:.3f}, level={best_prediction['confidence_level']})")
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
                
                # Preserve hyphens, normalize hyphen spacing, replace underscores with spaces, then title case
                # Example: "Dog-Toothed_Cat_Snake" -> "Dog-Toothed Cat Snake"
                s = re.sub(r"\s*-\s*", "-", class_name)
                pretty_name = s.replace("_", " ").strip().title()
                
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