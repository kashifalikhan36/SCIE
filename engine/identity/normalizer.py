import logging
import re
import unicodedata
from typing import Optional

from engine.identity.exceptions import NormalizationError

logger = logging.getLogger("SCIE.identity_engine.normalizer")


class NameNormalizer:
  """Robust multi-step name normalization pipeline.

  Steps applied in order:
  1. Unicode NFC normalization (accented chars canonical form).
  2. Lowercase.
  3. Expand common abbreviations (e.g. Dr. → dr, Jr. → jr).
  4. Remove punctuation except internal hyphens and apostrophes in contractions.
  5. Collapse multiple whitespace characters into a single space.
  6. Strip leading/trailing whitespace.
  7. Normalize initials: ``j w smith`` → ``j w smith`` (kept as-is, no dots).
  8. Remove repeated separator characters.

  All steps are deterministic and produce a canonical string suitable for
  RapidFuzz comparison.

  Example::

      NameNormalizer().normalize("John W. Smith")  # → "john w smith"
      NameNormalizer().normalize("Müller, Franz")  # → "muller franz"
      NameNormalizer().normalize("Dr. Emily O'Brien III") # → "dr emily o brien iii"
  """

  # Common honorifics / suffixes to strip (not remove entirely but normalize)
  _HONORIFICS = re.compile(
      r"\b(dr|mr|mrs|ms|miss|prof|rev|hon|sr|jr|md|phd|esq|ii|iii|iv)\b",
      re.IGNORECASE
  )

  def normalize(self, name: Optional[str]) -> str:
    """Normalizes a raw name string into a canonical lower-case form.

    Args:
        name: Raw name string (may be None, empty, or contain unicode).

    Returns:
        A normalized string.  Returns ``""`` for None / empty input.

    Raises:
        NormalizationError: If normalization fails unexpectedly.
    """
    try:
      if not name or not name.strip():
        return ""

      # 1. Unicode NFC normalization
      text = unicodedata.normalize("NFC", name)

      # 2. Transliterate common accented chars (ä→a, ö→o, ü→u, ñ→n, etc.)
      text = unicodedata.normalize("NFD", text)
      text = "".join(c for c in text if unicodedata.category(c) != "Mn")

      # 3. Lowercase
      text = text.lower()

      # 4. Remove periods that follow single letters (initials: J. → J)
      #    and standalone periods/commas
      text = re.sub(r"(?<=\b\w)\.", "", text)
      text = re.sub(r"[,;:!?\"()\[\]{}|\\/<>]", " ", text)

      # 5. Replace apostrophes in contractions with space (O'Brien → o brien)
      text = re.sub(r"'", " ", text)

      # 6. Remove standalone hyphens used as separators; keep word-internal ones
      text = re.sub(r"\s+-\s+", " ", text)

      # 7. Remove any remaining non-alphanumeric non-space characters
      text = re.sub(r"[^\w\s]", " ", text)

      # 8. Collapse whitespace
      text = re.sub(r"\s+", " ", text).strip()

      logger.debug(f"NameNormalizer: '{name}' → '{text}'")
      return text

    except Exception as exc:
      raise NormalizationError(f"Failed to normalize name '{name}': {exc}") from exc

  def normalize_email(self, email: Optional[str]) -> str:
    """Normalizes an email address (lowercase, strip whitespace).

    Args:
        email: Raw email string.

    Returns:
        Lowercase stripped email or empty string.
    """
    if not email:
      return ""
    return email.strip().lower()

  def extract_username(self, email: Optional[str]) -> str:
    """Extracts the username (local part) from an email address.

    Args:
        email: Raw email address.

    Returns:
        The part before ``@``, normalized.  Empty string if invalid.
    """
    if not email or "@" not in email:
      return ""
    return email.strip().lower().split("@")[0]

  def extract_domain(self, email: Optional[str]) -> str:
    """Extracts the domain (host part) from an email address.

    Args:
        email: Raw email address.

    Returns:
        The part after ``@``, normalized.  Empty string if invalid.
    """
    if not email or "@" not in email:
      return ""
    return email.strip().lower().split("@", 1)[1]
