"""Query interface for MXCP audit logs stored in JSONL format."""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Literal
import duckdb
import re

logger = logging.getLogger(__name__)

# Type aliases
EventType = Literal["tool", "resource", "prompt"]
PolicyDecision = Literal["allow", "deny", "warn", "n/a"]
Status = Literal["success", "error"]


class AuditQuery:
    """Query interface for reading audit logs from JSONL files using DuckDB."""

    def __init__(self, log_path: Path):
        """Initialize the query interface.

        Args:
            log_path: Path to the JSONL log file
        """
        self.log_path = log_path

        if not self.log_path.exists():
            raise FileNotFoundError(f"Audit log file not found: {self.log_path}")

    def _parse_since(self, since_str: str) -> datetime:
        """Parse a 'since' string into a datetime.

        Args:
            since_str: String like '10m', '2h', '1d'

        Returns:
            datetime object representing the cutoff time
        """
        # Parse the time unit
        match = re.match(r"^(\d+)([smhd])$", since_str.lower())
        if not match:
            raise ValueError(f"Invalid time format: {since_str}. Use format like '10m', '2h', '1d'")

        amount = int(match.group(1))
        unit = match.group(2)

        # Calculate timedelta
        if unit == "s":
            delta = timedelta(seconds=amount)
        elif unit == "m":
            delta = timedelta(minutes=amount)
        elif unit == "h":
            delta = timedelta(hours=amount)
        elif unit == "d":
            delta = timedelta(days=amount)
        else:
            raise ValueError(f"Unknown time unit: {unit}")

        # Return current time minus delta
        return datetime.now(timezone.utc) - delta

    def query_logs(
        self,
        tool: Optional[str] = None,
        resource: Optional[str] = None,
        prompt: Optional[str] = None,
        event_type: Optional[str] = None,
        policy: Optional[str] = None,
        status: Optional[str] = None,
        since: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """Query audit logs with optional filters."""
        conn = None
        try:
            # Use DuckDB in-memory to query the JSONL file
            conn = duckdb.connect(":memory:")

            # Build WHERE clause
            conditions = []

            # Name-based filters (tool/resource/prompt)
            if tool:
                conditions.append(f"type = 'tool' AND name = '{tool}'")
            elif resource:
                conditions.append(f"type = 'resource' AND name = '{resource}'")
            elif prompt:
                conditions.append(f"type = 'prompt' AND name = '{prompt}'")

            # Type filter
            if event_type:
                conditions.append(f"type = '{event_type}'")

            # Policy filter
            if policy:
                conditions.append(f"policy_decision = '{policy}'")

            # Status filter
            if status:
                conditions.append(f"status = '{status}'")

            # Time filter
            if since:
                since_time = self._parse_since(since).isoformat()
                conditions.append(f"timestamp >= '{since_time}'")

            # Build query using read_json_auto
            query = f"""
                SELECT * FROM read_json_auto('{self.log_path}')
            """

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY timestamp DESC"
            query += f" LIMIT {limit}"

            # Execute query
            result = conn.execute(query).fetchall()

            # Get column names
            columns = [desc[0] for desc in conn.description]

            # Convert to list of dicts
            logs = []
            for row in result:
                log_entry = dict(zip(columns, row))
                logs.append(log_entry)

            return logs

        except Exception as e:
            logger.error(f"Failed to query logs: {e}")
            raise
        finally:
            if conn:
                conn.close()

    def export_to_csv(
        self,
        output_path: Path,
        tool: Optional[str] = None,
        resource: Optional[str] = None,
        prompt: Optional[str] = None,
        event_type: Optional[str] = None,
        policy: Optional[str] = None,
        status: Optional[str] = None,
        since: Optional[str] = None,
    ) -> int:
        """Export audit logs to CSV file."""
        conn = None
        try:
            conn = duckdb.connect(":memory:")

            # Build WHERE clause
            conditions = []

            # Name-based filters (tool/resource/prompt)
            if tool:
                conditions.append(f"type = 'tool' AND name = '{tool}'")
            elif resource:
                conditions.append(f"type = 'resource' AND name = '{resource}'")
            elif prompt:
                conditions.append(f"type = 'prompt' AND name = '{prompt}'")

            # Type filter
            if event_type:
                conditions.append(f"type = '{event_type}'")

            # Policy filter
            if policy:
                conditions.append(f"policy_decision = '{policy}'")

            # Status filter
            if status:
                conditions.append(f"status = '{status}'")

            # Time filter
            if since:
                since_time = self._parse_since(since).isoformat()
                conditions.append(f"timestamp >= '{since_time}'")

            # Build query
            query = f"""
                SELECT * FROM read_json_auto('{self.log_path}')
            """

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY timestamp DESC"

            # Export directly to CSV
            export_query = f"COPY ({query}) TO '{output_path}' (HEADER, DELIMITER ',')"
            conn.execute(export_query)

            # Get row count
            count_query = f"SELECT COUNT(*) FROM ({query}) AS subquery"
            row_count = conn.execute(count_query).fetchone()[0]

            return row_count

        except Exception as e:
            logger.error(f"Failed to export logs: {e}")
            raise
        finally:
            if conn:
                conn.close()

    def export_to_duckdb(self, output_path: Path) -> int:
        """Export all audit logs to a DuckDB database file.

        Args:
            output_path: Path to the output DuckDB file

        Returns:
            Number of rows exported
        """
        conn = None
        try:
            # Connect to the output database
            conn = duckdb.connect(str(output_path))

            # Create table and import all data
            conn.execute(
                f"""
                CREATE TABLE logs AS 
                SELECT * FROM read_json_auto('{self.log_path}')
                ORDER BY timestamp DESC
            """
            )

            # Get row count
            row_count = conn.execute("SELECT COUNT(*) FROM logs").fetchone()[0]

            # Create indexes for better query performance
            conn.execute("CREATE INDEX idx_timestamp ON logs(timestamp)")
            conn.execute("CREATE INDEX idx_type ON logs(type)")
            conn.execute("CREATE INDEX idx_status ON logs(status)")
            conn.execute("CREATE INDEX idx_policy ON logs(policy_decision)")

            return row_count

        except Exception as e:
            logger.error(f"Failed to export to DuckDB: {e}")
            raise
        finally:
            if conn:
                conn.close()

    def get_summary_stats(self) -> Dict[str, Any]:
        """Get summary statistics about the audit logs.

        Returns:
            Dictionary with summary statistics
        """
        conn = None
        try:
            conn = duckdb.connect(":memory:")

            # Create a view for the JSONL data
            conn.execute(
                f"""
                CREATE VIEW logs AS 
                SELECT * FROM read_json_auto('{self.log_path}')
            """
            )

            stats = {}

            # Total count
            stats["total_events"] = conn.execute("SELECT COUNT(*) FROM logs").fetchone()[0]

            # Count by type
            type_counts = conn.execute(
                """
                SELECT type, COUNT(*) as count 
                FROM logs 
                GROUP BY type
            """
            ).fetchall()
            stats["by_type"] = {row[0]: row[1] for row in type_counts}

            # Count by status
            status_counts = conn.execute(
                """
                SELECT status, COUNT(*) as count 
                FROM logs 
                GROUP BY status
            """
            ).fetchall()
            stats["by_status"] = {row[0]: row[1] for row in status_counts}

            # Count by policy decision
            policy_counts = conn.execute(
                """
                SELECT policy_decision, COUNT(*) as count 
                FROM logs 
                GROUP BY policy_decision
            """
            ).fetchall()
            stats["by_policy"] = {row[0]: row[1] for row in policy_counts}

            # Time range
            time_range = conn.execute(
                """
                SELECT MIN(timestamp) as earliest, MAX(timestamp) as latest 
                FROM logs
            """
            ).fetchone()

            if time_range[0] and time_range[1]:
                stats["earliest_event"] = time_range[0]
                stats["latest_event"] = time_range[1]

            return stats

        except Exception as e:
            logger.error(f"Failed to get summary stats: {e}")
            raise
        finally:
            if conn:
                conn.close()
