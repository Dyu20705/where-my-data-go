"""
Source parsers for scholarly data feeds.
"""

from .base import BaseSourceParser
from .arxiv import ArxivParser
from .openalex import OpenAlexParser
from .crossref import CrossrefParser
from .semantic_scholar import SemanticScholarParser

__all__ = [
    "BaseSourceParser",
    "ArxivParser",
    "OpenAlexParser",
    "CrossrefParser",
    "SemanticScholarParser",
]
