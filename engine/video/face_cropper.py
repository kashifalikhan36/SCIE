import cv2
import logging
import numpy as np
from engine.video.schemas import DetectedFace
from engine.video.exceptions import FaceCropperError

logger = logging.getLogger("SCIE.video_engine.face_cropper")

class FaceCropper:
  """Crops, pads, and normalizes detected face regions for recognition processing."""

  def __init__(self, target_size: int = 112, padding_ratio: float = 0.15):
    self.target_size = target_size
    self.padding_ratio = padding_ratio

  def crop_face(self, frame: np.ndarray, face: DetectedFace) -> np.ndarray:
    """Crops the bounding box region from the frame, applies padding, and resizes to target_size."""
    if frame is None or frame.size == 0:
      raise FaceCropperError("Input frame is empty.")

    try:
      height, width, _ = frame.shape
      xmin_rel, ymin_rel, w_rel, h_rel = face.bbox

      # Convert normalized coords to absolute pixel coordinates
      xmin = int(round(xmin_rel * width))
      ymin = int(round(ymin_rel * height))
      w_px = int(round(w_rel * width))
      h_px = int(round(h_rel * height))

      # Calculate padding around face
      pad_w = int(round(w_px * self.padding_ratio))
      pad_h = int(round(h_px * self.padding_ratio))

      # Apply padding with boundaries check
      x1 = max(0, xmin - pad_w)
      y1 = max(0, ymin - pad_h)
      x2 = min(width, xmin + w_px + pad_w)
      y2 = min(height, ymin + h_px + pad_h)

      # Perform crop slice
      cropped = frame[y1:y2, x1:x2]
      if cropped.size == 0:
        logger.warning("Cropped bounding box resulted in empty slice. Returning default resized template.")
        # Return fallback zero placeholder image if slice was invalid/off-screen
        return np.zeros((self.target_size, self.target_size, 3), dtype=np.uint8)

      # Resize cropped face to standard size (e.g. 112x112 for InsightFace)
      normalized_face = cv2.resize(cropped, (self.target_size, self.target_size))
      return normalized_face

    except Exception as e:
      raise FaceCropperError(f"Failed to crop face region: {e}")
