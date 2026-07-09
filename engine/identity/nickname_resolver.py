import logging
from typing import Dict, List, Optional, Set

from engine.identity.normalizer import NameNormalizer
from engine.identity.schemas import AliasEvidence
from engine.identity.exceptions import NicknameResolverError

logger = logging.getLogger("SCIE.identity_engine.nickname_resolver")

# ──────────────────────────────────────────────────────────────────────────────
# Nickname / alias dictionary (canonical → aliases).
# Keyed by the normalized canonical first name, values are normalized aliases.
# Future expansion: load from a database or YAML file at startup.
# ──────────────────────────────────────────────────────────────────────────────
_NICKNAME_MAP: Dict[str, List[str]] = {
    # English common nicknames
    "william":    ["bill", "will", "billy", "liam"],
    "robert":     ["bob", "bobby", "rob", "robbie"],
    "richard":    ["rick", "ricky", "rich", "dick"],
    "james":      ["jim", "jimmy", "jamie"],
    "john":       ["johnny", "jon", "jack"],
    "jonathan":   ["john", "jon", "jonny"],
    "joseph":     ["joe", "joey"],
    "michael":    ["mike", "mikey", "mick"],
    "thomas":     ["tom", "tommy"],
    "charles":    ["charlie", "chuck", "chas"],
    "george":     ["georgie"],
    "henry":      ["harry", "hank"],
    "edward":     ["ed", "eddie", "ned", "ted"],
    "andrew":     ["andy", "drew"],
    "christopher": ["chris"],
    "matthew":    ["matt"],
    "anthony":    ["tony"],
    "daniel":     ["dan", "danny"],
    "david":      ["dave", "davy"],
    "stephen":    ["steve", "stevie"],
    "steven":     ["steve", "stevie"],
    "alexander":  ["alex", "al", "alec", "xander"],
    "nicholas":   ["nick", "nico"],
    "benjamin":   ["ben", "benny"],
    "samuel":     ["sam", "sammy"],
    "patrick":    ["pat", "paddy"],
    "peter":      ["pete"],
    "gregory":    ["greg"],
    "timothy":    ["tim", "timmy"],
    "lawrence":   ["larry", "lars"],
    "leonard":    ["len", "lenny", "leo"],
    "raymond":    ["ray"],
    "donald":     ["don", "donny"],
    "gerald":     ["gerry", "jerry"],
    "kenneth":    ["ken", "kenny"],
    "vincent":    ["vince", "vic"],
    "walter":     ["walt", "wally"],
    "albert":     ["al", "bert"],
    "arthur":     ["art"],
    "eugene":     ["gene"],
    "ernest":     ["ernie"],
    "frederic":   ["fred", "freddy"],
    "frederick":  ["fred", "freddy"],
    "harold":     ["harry", "hal"],
    "howard":     ["howie"],
    "jerome":     ["jerry"],
    "leonard":    ["leo", "len"],
    "philip":     ["phil"],
    "phillip":    ["phil"],
    "reginald":   ["reggie", "reg"],
    "rodney":     ["rod"],
    "roger":      ["dodge"],
    "ronald":     ["ron", "ronnie"],
    "russell":    ["russ"],
    "stanley":    ["stan"],
    "theodore":   ["ted", "theo"],
    "victor":     ["vic"],
    # Female names
    "elizabeth":  ["liz", "beth", "eliza", "betty", "ellie", "lisa", "libby", "bess"],
    "katherine":  ["kate", "kathy", "kat", "kitty"],
    "catherine":  ["kate", "cathy", "cat", "cate"],
    "margaret":   ["maggie", "meg", "peg", "peggy", "marge"],
    "jennifer":   ["jen", "jenny"],
    "jessica":    ["jess", "jessie"],
    "stephanie":  ["steph"],
    "alexandra":  ["alex", "lexi", "sasha"],
    "samantha":   ["sam", "sammie"],
    "patricia":   ["pat", "patty", "trish"],
    "barbara":    ["barb", "barbie"],
    "carolyn":    ["carol", "carrie"],
    "dorothy":    ["dot", "dotty"],
    "rebecca":    ["becca", "becky"],
    "kimberly":   ["kim"],
    "deborah":    ["deb", "debbie"],
    "judith":     ["judy", "jude"],
    "sandra":     ["sandy"],
    "virginia":   ["ginny", "ginger"],
    "victoria":   ["vicky", "vicki", "tori"],
    "theodora":   ["teddy", "thea"],
    "jacqueline": ["jackie", "jacqui"],
    "josephine":  ["josie", "jo"],
    "helen":      ["ellie"],
    "eleanor":    ["nellie", "ellie", "nell"],
    # International / multi-cultural names
    "muhammad":   ["mohammad", "mohammed", "mo"],
    "mohammad":   ["muhammad", "mohammed", "mo"],
    "mohammed":   ["muhammad", "mohammad", "mo"],
    "ibrahim":    ["abe", "ibrahim"],
    "ali":        ["al"],
    "wei":        ["vivian"],
    "chen":       ["charlie"],
    "jose":       ["joe", "pepe"],
    "juan":       ["john"],
    "carlo":      ["charles", "charlie"],
    "luigi":      ["louis", "lou"],
    "pierre":     ["peter", "pete"],
    "jean":       ["john", "jane"],
    "hans":       ["john"],
    "erika":      ["eric"],
}

# Build reverse map: alias → set of canonical names
_REVERSE_MAP: Dict[str, Set[str]] = {}
for _canonical, _aliases in _NICKNAME_MAP.items():
    for _alias in _aliases:
        _REVERSE_MAP.setdefault(_alias, set()).add(_canonical)


class NicknameResolver:
  """Resolves candidate names into all known aliases and vice-versa.

  Uses a curated nickname dictionary with bidirectional lookup.
  Future-proof: the dictionary can be extended at runtime via
  ``register_alias()``.

  Example::

      resolver = NicknameResolver()
      resolver.expand("William")   # → ["william", "bill", "will", "billy", "liam"]
      resolver.canonicalize("bob") # → ["robert"]
  """

  def __init__(self) -> None:
    self._normalizer = NameNormalizer()
    # Mutable copies so runtime additions don't affect the module-level dicts
    self._map: Dict[str, List[str]] = {k: list(v) for k, v in _NICKNAME_MAP.items()}
    self._reverse: Dict[str, Set[str]] = {k: set(v) for k, v in _REVERSE_MAP.items()}

  def expand(self, name: Optional[str]) -> List[str]:
    """Returns all normalized aliases for a given name (including the name itself).

    If ``name`` is already a nickname, also returns the canonical form and all
    sibling aliases.

    Args:
        name: Raw candidate or display name.

    Returns:
        Deduplicated list of normalized name variants.  Always contains at least
        the normalized form of ``name`` itself.
    """
    try:
      if not name:
        return []

      norm = self._normalizer.normalize(name)
      if not norm:
        return []

      # Split into tokens and work with the first token (first name)
      first_token = norm.split()[0] if norm.split() else norm
      variants: Set[str] = {norm}

      # 1. Forward: canonical → aliases
      if first_token in self._map:
        for alias in self._map[first_token]:
          # Replace first token with the alias, keep last name parts
          parts = norm.split()
          alias_name = " ".join([alias] + parts[1:])
          variants.add(alias_name)

      # 2. Reverse: alias → canonical
      if first_token in self._reverse:
        for canonical in self._reverse[first_token]:
          parts = norm.split()
          canon_name = " ".join([canonical] + parts[1:])
          variants.add(canon_name)
          # Also add aliases of the canonical
          if canonical in self._map:
            for sibling_alias in self._map[canonical]:
              sibling_name = " ".join([sibling_alias] + parts[1:])
              variants.add(sibling_name)

      result = sorted(variants)
      logger.debug(f"NicknameResolver: expanded '{name}' → {result}")
      return result

    except Exception as exc:
      raise NicknameResolverError(f"Failed to expand name '{name}': {exc}") from exc

  def canonicalize(self, name: Optional[str]) -> List[str]:
    """Returns the canonical form(s) for a given alias.

    Args:
        name: Potentially an alias or nickname.

    Returns:
        List of canonical names.  Empty list if no canonical form found.
    """
    try:
      if not name:
        return []
      norm = self._normalizer.normalize(name)
      first_token = norm.split()[0] if norm.split() else norm
      return list(self._reverse.get(first_token, []))
    except Exception as exc:
      raise NicknameResolverError(f"Failed to canonicalize '{name}': {exc}") from exc

  def match_alias(
      self,
      candidate_name: Optional[str],
      participant_name: Optional[str],
  ) -> AliasEvidence:
    """Checks whether participant_name matches any alias of candidate_name.

    Args:
        candidate_name: The expected candidate name (from meeting metadata).
        participant_name: The observed participant display name.

    Returns:
        AliasEvidence with a score ≥ 0.60 when an alias match is found.
    """
    try:
      if not candidate_name or not participant_name:
        return AliasEvidence(
            score=0.0, confidence=0.0,
            reasons=["Missing candidate or participant name for alias matching."]
        )

      candidate_variants = self.expand(candidate_name)
      norm_participant = self._normalizer.normalize(participant_name)

      for variant in candidate_variants:
        if variant == norm_participant:
          # Exact alias match
          return AliasEvidence(
              score=0.80,
              confidence=0.75,
              reasons=[f"Alias match: '{participant_name}' → '{variant}' ← '{candidate_name}'"],
              matched_alias=variant,
              canonical_name=self._normalizer.normalize(candidate_name),
              alias_source="nickname_dict"
          )

        # Partial / prefix alias match (e.g. "Bob" matches "Robert Smith")
        if norm_participant and variant.split()[0] == norm_participant.split()[0]:
          return AliasEvidence(
              score=0.65,
              confidence=0.60,
              reasons=[f"First-name alias match: '{norm_participant.split()[0]}' ↔ '{variant.split()[0]}'"],
              matched_alias=variant.split()[0],
              canonical_name=self._normalizer.normalize(candidate_name),
              alias_source="nickname_dict"
          )

      return AliasEvidence(
          score=0.0, confidence=0.0,
          reasons=[f"No alias match found between '{candidate_name}' and '{participant_name}'."]
      )

    except Exception as exc:
      raise NicknameResolverError(f"Alias match failed: {exc}") from exc

  def register_alias(self, canonical: str, alias: str) -> None:
    """Dynamically registers a new alias at runtime.

    Args:
        canonical: Canonical (authoritative) name form.
        alias: Alternative name to add.
    """
    norm_canonical = self._normalizer.normalize(canonical)
    norm_alias = self._normalizer.normalize(alias)
    if not norm_canonical or not norm_alias:
      return
    self._map.setdefault(norm_canonical, [])
    if norm_alias not in self._map[norm_canonical]:
      self._map[norm_canonical].append(norm_alias)
    self._reverse.setdefault(norm_alias, set()).add(norm_canonical)
    logger.info(f"NicknameResolver: Registered alias '{norm_alias}' → '{norm_canonical}'")
