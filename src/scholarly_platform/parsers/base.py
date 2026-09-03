"""
Base class and common utilities for source data parsers.
"""

from abc import ABC, abstractmethod
import json
import re
from typing import Dict, Any, Generator, Optional
from pathlib import Path

from ..models import ParsedWork


class BaseSourceParser(ABC):
    """Abstract base parser for external scholarly data feeds."""

    source_name: str = "base"

    @abstractmethod
    def parse_record(self, raw: Dict[str, Any]) -> ParsedWork:
        """Parses a single source record dictionary into a normalized ParsedWork."""
        pass

    def parse_jsonl_line(self, line: str) -> ParsedWork:
        """Parses a single JSON line."""
        data = json.loads(line.strip())
        return self.parse_record(data)

    def parse_file(self, file_path: str) -> Generator[ParsedWork, None, None]:
        """Streams ParsedWork objects from a JSONL file."""
        path = Path(file_path)
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if line_str:
                    yield self.parse_jsonl_line(line_str)

    @staticmethod
    def clean_text(text: Optional[str]) -> Optional[str]:
        """Cleans whitespace, newlines, and unprintable characters from text."""
        if not text:
            return None
        cleaned = re.sub(r"\s+", " ", text).strip()
        return cleaned if cleaned else None
