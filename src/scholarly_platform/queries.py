"""
Analytical SQL Queries for Technological Trend Mining.
Provides optimized queries for citation velocity, venue authority, and co-authorship networks.
"""

from typing import List, Dict, Any
import duckdb


class ScholarlyAnalytics:
    """Encapsulates analytical queries over the canonical Gold layer."""

    @staticmethod
    def citation_velocity(
        con: duckdb.DuckDBPyConnection, min_year: int = 2015, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Computes citation velocity and influential growth rates for trend mining.
        """
        sql = """
        SELECT 
            w.canonical_work_id,
            w.title,
            w.publication_year,
            v.name AS venue_name,
            w.citation_count,
            w.influential_citation_count,
            COUNT(c.citing_work_id) AS inbound_citation_edges,
            ROUND(
                w.citation_count::DOUBLE / GREATEST(1, EXTRACT(YEAR FROM CURRENT_DATE) - w.publication_year + 1),
                2
            ) AS citation_velocity
        FROM canonical_works w
        LEFT JOIN canonical_venues v ON w.canonical_venue_id = v.canonical_venue_id
        LEFT JOIN canonical_citations c ON w.canonical_work_id = c.cited_work_id
        WHERE w.is_stub = FALSE AND (w.publication_year >= ? OR w.publication_year IS NULL)
        GROUP BY 
            w.canonical_work_id, w.title, w.publication_year, v.name,
            w.citation_count, w.influential_citation_count
        ORDER BY w.influential_citation_count DESC, citation_velocity DESC
        LIMIT ?;
        """
        df = con.execute(sql, [min_year, limit]).fetchall()
        cols = [
            "canonical_work_id",
            "title",
            "publication_year",
            "venue_name",
            "citation_count",
            "influential_citation_count",
            "inbound_citation_edges",
            "citation_velocity",
        ]
        return [dict(zip(cols, row)) for row in df]

    @staticmethod
    def coauthorship_network(
        con: duckdb.DuckDBPyConnection, min_collaborations: int = 1, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Extracts co-authorship collaboration graph edges.
        """
        sql = """
        SELECT 
            a1.display_name AS author_1,
            a2.display_name AS author_2,
            COUNT(DISTINCT wa1.canonical_work_id) AS shared_works
        FROM canonical_work_authors wa1
        JOIN canonical_work_authors wa2 
            ON wa1.canonical_work_id = wa2.canonical_work_id 
           AND wa1.canonical_author_id < wa2.canonical_author_id
        JOIN canonical_authors a1 ON wa1.canonical_author_id = a1.canonical_author_id
        JOIN canonical_authors a2 ON wa2.canonical_author_id = a2.canonical_author_id
        GROUP BY author_1, author_2
        HAVING COUNT(DISTINCT wa1.canonical_work_id) >= ?
        ORDER BY shared_works DESC
        LIMIT ?;
        """
        df = con.execute(sql, [min_collaborations, limit]).fetchall()
        cols = ["author_1", "author_2", "shared_works"]
        return [dict(zip(cols, row)) for row in df]

    @staticmethod
    def venue_impact(
        con: duckdb.DuckDBPyConnection, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Aggregates total publications and citations by venue.
        """
        sql = """
        SELECT 
            v.name AS venue_name,
            v.venue_type,
            COUNT(w.canonical_work_id) AS total_works,
            SUM(w.citation_count) AS total_citations,
            ROUND(AVG(w.citation_count), 2) AS avg_citations_per_work
        FROM canonical_venues v
        JOIN canonical_works w ON v.canonical_venue_id = w.canonical_venue_id
        WHERE w.is_stub = FALSE
        GROUP BY v.name, v.venue_type
        ORDER BY total_citations DESC
        LIMIT ?;
        """
        df = con.execute(sql, [limit]).fetchall()
        cols = ["venue_name", "venue_type", "total_works", "total_citations", "avg_citations_per_work"]
        return [dict(zip(cols, row)) for row in df]

    @staticmethod
    def work_provenance_audit(
        con: duckdb.DuckDBPyConnection, canonical_work_id: str
    ) -> List[Dict[str, Any]]:
        """
        Retrieves full attribute-level lineage for a specific canonical work.
        """
        sql = """
        SELECT 
            p.attribute_name,
            p.winning_source,
            p.source_observation_id,
            p.resolution_rule,
            p.selected_at,
            obs.source_work_id
        FROM canonical_work_provenance p
        JOIN source_work_observations obs ON p.source_observation_id = obs.observation_id
        WHERE p.canonical_work_id = ?
        ORDER BY p.attribute_name;
        """
        df = con.execute(sql, [canonical_work_id]).fetchall()
        cols = [
            "attribute_name",
            "winning_source",
            "source_observation_id",
            "resolution_rule",
            "selected_at",
            "source_work_id",
        ]
        return [dict(zip(cols, row)) for row in df]
