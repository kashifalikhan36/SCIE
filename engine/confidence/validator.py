"""
Evidence Validator Module for the SCIE Confidence Engine (`engine/confidence/validator.py`).

Validates incoming raw evidence objects across:
- `participant_id`: Must be non-empty string.
- `source`: Must be non-empty and recognized (or safely fallback).
- `score`: Must be numeric and finite.
- `confidence`: Must be numeric and finite [0.0, 1.0] bounds.
- `timestamp`: Must be positive finite timestamp.

Logs malformed evidence cleanly without crashing the processing loop.
"""
import math
from typing import Optional, Dict, Any
from pydantic import ValidationError
from engine.confidence.constants import ALL_EVIDENCE_SOURCES
from engine.confidence.schemas import Evidence
from engine.confidence.models import RawEvidenceItem
from engine.confidence.logger import logger
from engine.confidence.utils import clamp, current_timestamp_sec


class EvidenceValidator:
  """Validates raw incoming evidence dictionaries or objects without crashing."""

  def validate_and_parse(self, raw_input: Any) -> Optional[RawEvidenceItem]:
    """Validate raw evidence dictionary or `Evidence` model into a clean `RawEvidenceItem`.

    Returns `None` if the input is malformed or violates mandatory integrity boundaries.
    """
    if raw_input is None:
      logger.warning("Rejecting null evidence input")
      return None

    # If already a dictionary, convert via schema
    data_dict: Dict[str, Any]
    if isinstance(raw_input, Evidence):
      data_dict = raw_input.model_dump()
    elif isinstance(raw_input, dict):
      data_dict = raw_input
    else:
      logger.error(f"Rejecting unsupported evidence format: {type(raw_input)}")
      return None

    try:
      # Extract mandatory fields
      pid = str(data_dict.get("participant_id", "")).strip()
      if not pid:
        logger.warning("Rejecting evidence with missing or empty participant_id")
        return None

      source = str(data_dict.get("source", "")).strip().lower()
      if not source:
        logger.warning(f"Rejecting evidence from participant {pid} due to empty source")
        return None

      if source not in ALL_EVIDENCE_SOURCES:
        logger.debug(f"Received evidence with non-standard source '{source}' for {pid}; allowing with generic handling")

      # Extract numeric metrics safely
      raw_score = data_dict.get("score")
      if raw_score is None or isinstance(raw_score, (bool, str)) and not str(raw_score).replace(".", "", 1).lstrip("-").isdigit():
        logger.warning(f"Rejecting evidence ({source}) for {pid}: non-numeric score ({raw_score})")
        return None
      score_float = float(raw_score)
      if math.isnan(score_float) or math.isinf(score_float):
        logger.warning(f"Rejecting evidence ({source}) for {pid}: score is NaN or Inf")
        return None

      raw_conf = data_dict.get("confidence")
      if raw_conf is None or isinstance(raw_conf, (bool, str)) and not str(raw_conf).replace(".", "", 1).lstrip("-").isdigit():
        logger.warning(f"Rejecting evidence ({source}) for {pid}: non-numeric confidence ({raw_conf})")
        return None
      conf_float = float(raw_conf)
      if math.isnan(conf_float) or math.isinf(conf_float):
        logger.warning(f"Rejecting evidence ({source}) for {pid}: confidence is NaN or Inf")
        return None

      # Validate timestamp
      raw_ts = data_dict.get("timestamp")
      if raw_ts is None or isinstance(raw_ts, (bool, str)) and not str(raw_ts).replace(".", "", 1).lstrip("-").isdigit():
        ts_float = current_timestamp_sec()
        logger.debug(f"Missing/invalid timestamp in {source} evidence for {pid}; substituting current epoch")
      else:
        ts_float = float(raw_ts)
        if math.isnan(ts_float) or math.isinf(ts_float) or ts_float <= 0.0:
          ts_float = current_timestamp_sec()

      # Check for extreme future timestamps (clock drift > 1 hr)
      now_sec = current_timestamp_sec()
      if ts_float > now_sec + 3600.0:
        logger.warning(f"Rejecting evidence ({source}) for {pid} with extreme future timestamp ({ts_float})")
        return None

      reason_str = str(data_dict.get("reason", f"Verified upstream {source} signal")).strip()
      if not reason_str:
        reason_str = f"Verified {source} signal"

      metadata_dict = data_dict.get("metadata") if isinstance(data_dict.get("metadata"), dict) else {}

      return RawEvidenceItem(
          participant_id=pid,
          source=source,
          score=score_float,
          confidence=clamp(conf_float, 0.0, 1.0),
          reason=reason_str,
          timestamp=ts_float,
          metadata=metadata_dict
      )

    except (ValueError, TypeError, ValidationError) as e:
      logger.error(f"Malformed evidence input encountered: {e}", exc_info=True)
      return None
