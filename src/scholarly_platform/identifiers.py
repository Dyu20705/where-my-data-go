"""
Deterministic Identifier Normalizers and Canonical Identity Generator.
Implements academic identifier parsing (DOI, arXiv, ORCID, ROR) and
deterministic surrogate key generation based on isolated UUID namespaces.
"""

import hashlib
import re
import uuid
from typing import Optional

# Dedicated UUID Namespaces for Scholarly Canonical Entities
NAMESPACE_CANONICAL_WORK = uuid.uuid5(uuid.NAMESPACE_DNS, "work.scholarly.platform")
NAMESPACE_CANONICAL_AUTHOR = uuid.uuid5(uuid.NAMESPACE_DNS, "author.scholarly.platform")
NAMESPACE_CANONICAL_INSTITUTION = uuid.uuid5(uuid.NAMESPACE_DNS, "institution.scholarly.platform")
NAMESPACE_CANONICAL_VENUE = uuid.uuid5(uuid.NAMESPACE_DNS, "venue.scholarly.platform")


def compute_payload_hash(payload_str: str) -> str:
    """Computes deterministic SHA-256 hex digest of a string payload."""
    return hashlib.sha256(payload_str.encode("utf-8")).hexdigest()


def normalize_doi(raw: Optional[str]) -> Optional[str]:
    """
    Normalizes a Digital Object Identifier (DOI) according to ISO 26324.
    Strips URL prefixes, 'doi:' prefixes, trims whitespace, and converts to lowercase.
    Validates standard DOI syntax: 10.\\d{4,9}/.+
    """
    if not raw or not isinstance(raw, str):
        return None
    cleaned = raw.strip().lower()
    cleaned = re.sub(r"^https?://(dx\.)?doi\.org/", "", cleaned)
    cleaned = re.sub(r"^doi:\s*", "", cleaned)
    cleaned = cleaned.strip()

    if re.match(r"^10\.\d{4,9}/[^\s]+$", cleaned):
        return cleaned
    return None


def normalize_arxiv_id(raw: Optional[str], strip_version: bool = True) -> Optional[str]:
    """
    Normalizes an arXiv identifier.
    Supports modern format (YYMM.NNNNN) and legacy format (arch-ive/YYMMNNN).
    If strip_version is True, strips trailing 'vN' version suffixes to represent the canonical work.
    """
    if not raw or not isinstance(raw, str):
        return None
    cleaned = raw.strip().lower()
    cleaned = re.sub(r"^https?://arxiv\.org/(abs|pdf)/", "", cleaned)
    cleaned = re.sub(r"^arxiv:\s*", "", cleaned)
    cleaned = cleaned.strip()

    if strip_version:
        cleaned = re.sub(r"v\d+$", "", cleaned)

    # Validate modern format (e.g. 1706.03762 or 2301.00001)
    if re.match(r"^\d{4}\.\d{4,5}(v\d+)?$", cleaned):
        return cleaned
    # Validate legacy format (e.g. math/0501234 or hep-th/9901001)
    if re.match(r"^[a-z\-]+(\.[a-z]{2})?/\d{7}(v\d+)?$", cleaned):
        return cleaned
    return None


def validate_orcid_checksum(orcid_digits: str) -> bool:
    """Validates ISO/IEC 7064 MOD 11-2 check-digit for ORCID."""
    if len(orcid_digits) != 16:
        return False
    total = 0
    for digit in orcid_digits[:15]:
        total = (total + int(digit)) * 2
    remainder = total % 11
    result = (12 - remainder) % 11
    check_char = "X" if result == 10 else str(result)
    return orcid_digits[15].upper() == check_char


def normalize_orcid(raw: Optional[str]) -> Optional[str]:
    """
    Normalizes and validates an Open Researcher and Contributor ID (ORCID).
    Format: 0000-0000-0000-000X with valid ISO/IEC 7064 MOD 11-2 checksum.
    """
    if not raw or not isinstance(raw, str):
        return None
    cleaned = raw.strip()
    cleaned = re.sub(r"^https?://orcid\.org/", "", cleaned)
    cleaned = cleaned.strip()

    match = re.match(r"^(\d{4})-(\d{4})-(\d{4})-([\dX])$", cleaned, re.IGNORECASE)
    if not match:
        digits_only = re.sub(r"[^0-9X]", "", cleaned.upper())
        if len(digits_only) == 16:
            cleaned = f"{digits_only[0:4]}-{digits_only[4:8]}-{digits_only[8:12]}-{digits_only[12:16]}"
        else:
            return None

    raw_digits = cleaned.replace("-", "").upper()
    if validate_orcid_checksum(raw_digits):
        return cleaned.upper()
    return None


def normalize_ror_id(raw: Optional[str]) -> Optional[str]:
    """
    Normalizes a Research Organization Registry (ROR) identifier.
    Extracts canonical URL format: https://ror.org/0xxxxxxNN
    """
    if not raw or not isinstance(raw, str):
        return None
    cleaned = raw.strip().lower()
    cleaned = re.sub(r"^https?://ror\.org/", "", cleaned)
    if re.match(r"^0[a-hj-km-np-tv-z0-9]{6}\d{2}$", cleaned):
        return f"https://ror.org/{cleaned}"
    return None


def slugify_text(text: Optional[str]) -> str:
    """Generates a normalized alphanumeric lowercase slug for matching."""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def compute_work_fingerprint(
    title: Optional[str],
    publication_year: Optional[int] = None,
    first_author_name: Optional[str] = None,
) -> str:
    """
    Generates a deterministic composite fingerprint for candidate matching.
    NOTE: Fingerprint matches are CANDIDATE_ONLY and must NOT trigger auto-merge.
    """
    title_slug = slugify_text(title)
    year_str = str(publication_year or "unknown")
    author_slug = slugify_text(first_author_name)
    raw = f"{title_slug}|{year_str}|{author_slug}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def mint_canonical_work_id(primary_anchor_key: str) -> str:
    """
    Mints a deterministic canonical work ID (UUIDv5) from a resolved primary anchor key.
    Primary anchor key format: 'doi:10.1234/...', 'arxiv:1706.03762', or 'cluster:<cluster_id>'.
    """
    return str(uuid.uuid5(NAMESPACE_CANONICAL_WORK, primary_anchor_key))


def mint_canonical_author_id(primary_author_key: str) -> str:
    """
    Mints a deterministic canonical author ID (UUIDv5) from a primary author key.
    Format: 'orcid:0000-0002-1825-0097' or 'source:<provider>:<id>'.
    """
    return str(uuid.uuid5(NAMESPACE_CANONICAL_AUTHOR, primary_author_key))


def mint_canonical_venue_id(normalized_venue_name: str, issn: Optional[str] = None) -> str:
    """Mints a deterministic canonical venue ID (UUIDv5)."""
    if issn:
        clean_issn = issn.strip().lower()
        return str(uuid.uuid5(NAMESPACE_CANONICAL_VENUE, f"issn:{clean_issn}"))
    slug = slugify_text(normalized_venue_name)
    return str(uuid.uuid5(NAMESPACE_CANONICAL_VENUE, f"name:{slug}"))


def mint_canonical_institution_id(ror_id: Optional[str] = None, name: Optional[str] = None) -> str:
    """Mints a deterministic canonical institution ID (UUIDv5)."""
    norm_ror = normalize_ror_id(ror_id)
    if norm_ror:
        return str(uuid.uuid5(NAMESPACE_CANONICAL_INSTITUTION, f"ror:{norm_ror}"))
    slug = slugify_text(name)
    return str(uuid.uuid5(NAMESPACE_CANONICAL_INSTITUTION, f"name:{slug}"))
