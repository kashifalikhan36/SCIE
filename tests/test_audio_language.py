import pytest
from engine.audio.language_detector import LanguageDetector
from engine.audio.schemas import LanguageDetectionResult

@pytest.mark.asyncio
async def test_language_detector():
  """Test that LanguageDetector classifies spoken language correctly (using fallback)."""
  detector = LanguageDetector()
  
  # 1. Normal execution
  res = await detector.detect_language(b"\x01\x02" * 1000)
  assert isinstance(res, LanguageDetectionResult)
  assert res.language == "en"
  assert res.confidence >= 0.90
  
  # 2. Empty input
  res_empty = await detector.detect_language(b"")
  assert res_empty.language == "en"
  assert res_empty.confidence == 1.0
