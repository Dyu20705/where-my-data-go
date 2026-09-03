"""
Domain Models and Typed Data Structures for Canonical Scholarly Platform.
Represents Bronze runs/manifest/quarantine, Silver observations, and Gold canonical entities.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import List, Optional, Dict, Any


def utc_now() -> datetime:
    """Returns current UTC datetime."""
    return datetime.now(timezone.utc)



@dataclass
class IngestionRun:
    """Represents a discrete pipeline execution batch and run-level lineage."""
    run_id: str
    source_name: str
    input_uri: Optional[str] = None
    input_hash: str = ""
    record_count: int = 0
    accepted_count: int = 0
    rejected_count: int = 0
    error_count: int = 0
    pipeline_version: str = "0.1.0"
    parser_version: str = "0.1.0"
    schema_version: str = "1.0.0"
    started_at: datetime = field(default_factory=utc_now)
    completed_at: Optional[datetime] = None
    status: str = "IN_PROGRESS"


@dataclass
class RawManifestRecord:
    """Represents an immutable record in the Bronze landing manifest."""
    raw_record_id: str
    run_id: str
    source_name: str
    payload_hash: str
    payload: Dict[str, Any]
    source_record_id: Optional[str] = None
    ingested_at: datetime = field(default_factory=utc_now)


@dataclass
class QuarantineRecord:
    """Represents a rejected or malformed record in Bronze quarantine."""
    quarantine_id: str
    run_id: str
    source_name: str
    raw_payload: Dict[str, Any]
    error_type: str
    error_message: str
    quarantined_at: datetime = field(default_factory=utc_now)


@dataclass
class ParsedAuthor:
    """Represents an author mention extracted from a source record."""
    raw_name: str
    position: int
    orcid: Optional[str] = None
    source_author_id: Optional[str] = None
    raw_affiliation: Optional[str] = None
    institution_name: Optional[str] = None
    institution_ror: Optional[str] = None
    institution_country: Optional[str] = None
    is_corresponding: bool = False


@dataclass
class ParsedCitation:
    """Represents a citation reference extracted from a source record."""
    cited_doi: Optional[str] = None
    cited_arxiv_id: Optional[str] = None
    cited_source_id: Optional[str] = None
    raw_citation_string: Optional[str] = None
    is_influential: bool = False
    citation_intents: List[str] = field(default_factory=list)


@dataclass
class ParsedWork:
    """Represents a parsed, normalized work observation before database staging."""
    source_name: str
    source_work_id: str
    title: str
    abstract: Optional[str] = None
    publication_year: Optional[int] = None
    publication_date: Optional[date] = None
    normalized_doi: Optional[str] = None
    normalized_arxiv_id: Optional[str] = None
    raw_venue_name: Optional[str] = None
    venue_issn: Optional[str] = None
    venue_type: Optional[str] = None
    citation_count: int = 0
    influential_citation_count: int = 0
    authors: List[ParsedAuthor] = field(default_factory=list)
    citations: List[ParsedCitation] = field(default_factory=list)
    external_ids: Dict[str, str] = field(default_factory=dict)
    observed_at: datetime = field(default_factory=utc_now)
    raw_payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SourceWorkObservation:
    """Represents an immutable record-level observation in the Silver layer."""
    observation_id: str
    run_id: str
    source_name: str
    source_work_id: str
    title: str
    observed_at: datetime
    raw_record_id: Optional[str] = None
    normalized_doi: Optional[str] = None
    normalized_arxiv_id: Optional[str] = None
    abstract: Optional[str] = None
    publication_date: Optional[date] = None
    publication_year: Optional[int] = None
    raw_venue_name: Optional[str] = None
    citation_count: int = 0
    influential_citation_count: int = 0
    raw_authors: List[Dict[str, Any]] = field(default_factory=list)
    raw_citations: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class CanonicalWork:
    """Represents an authoritative canonical work entity in the Gold layer."""
    canonical_work_id: str
    title: str
    abstract: Optional[str] = None
    publication_year: Optional[int] = None
    publication_date: Optional[date] = None
    canonical_doi: Optional[str] = None
    canonical_arxiv_id: Optional[str] = None
    canonical_venue_id: Optional[str] = None
    is_stub: bool = False
    stub_reason: Optional[str] = None
    created_from_source: Optional[str] = None
    citation_count: int = 0
    influential_citation_count: int = 0
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class CanonicalVenue:
    """Represents an authoritative venue in the Gold layer."""
    canonical_venue_id: str
    name: str
    normalized_name: str
    venue_type: Optional[str] = "UNSPECIFIED"
    tier: Optional[str] = "UNRANKED"
    issn: Optional[str] = None


@dataclass
class CanonicalInstitution:
    """Represents an authoritative institution in the Gold layer."""
    canonical_inst_id: str
    name: str
    ror_id: Optional[str] = None
    country_code: Optional[str] = None
    homepage_url: Optional[str] = None


@dataclass
class CanonicalAuthor:
    """Represents an authoritative researcher in the Gold layer."""
    canonical_author_id: str
    display_name: str
    orcid: Optional[str] = None
    aliases: List[str] = field(default_factory=list)


@dataclass
class CanonicalWorkIdentifier:
    """Represents an identifier mapping in the Gold layer."""
    identifier_type: str
    normalized_value: str
    canonical_work_id: str
    raw_value: str


@dataclass
class CanonicalWorkAuthor:
    """Represents a work-author junction row in the Gold layer."""
    canonical_work_id: str
    canonical_author_id: str
    author_position: int
    canonical_inst_id: Optional[str] = None
    raw_author_name: Optional[str] = None
    raw_affiliation_string: Optional[str] = None
    is_corresponding: bool = False


@dataclass
class CanonicalCitation:
    """Represents a directed citation edge in the Gold layer."""
    citing_work_id: str
    cited_work_id: str
    is_influential: bool = False
    citation_intents: List[str] = field(default_factory=list)
    source_provider: str = ""


@dataclass
class CanonicalWorkProvenance:
    """Represents attribute-level lineage pointing to the winning source observation."""
    canonical_work_id: str
    attribute_name: str
    winning_source: str
    source_observation_id: str
    resolution_rule: str
    selected_at: datetime = field(default_factory=utc_now)


@dataclass
class MetricsProvenance:
    """Represents a time-series metric snapshot."""
    canonical_work_id: str
    metric_name: str
    metric_value: float
    source_provider: str
    run_id: str
    observed_at: datetime
    source_observation_id: Optional[str] = None
