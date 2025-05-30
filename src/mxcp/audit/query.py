"""Query interface for MXCP audit logs."""

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
    """Query interface for reading audit logs from DuckDB."""
    
    def __init__(self, db_path: Path):
        """Initialize the query interface.
        
        Args:
            db_path: Path to the DuckDB database file
        """
        self.db_path = db_path
        
        if not self.db_path.exists():
            raise FileNotFoundError(f"Audit database not found: {self.db_path}")
    
    def _parse_since(self, since_str: str) -> datetime:
        """Parse a 'since' string into a datetime.
        
        Args:
            since_str: String like '10m', '2h', '1d'
            
        Returns:
            datetime object representing the cutoff time
        """
        # Parse the time unit
        match = re.match(r'^(\d+)([smhd])$', since_str.lower())
        if not match:
            raise ValueError(f"Invalid time format: {since_str}. Use format like '10m', '2h', '1d'")
        
        amount = int(match.group(1))
        unit = match.group(2)
        
        # Calculate timedelta
        if unit == 's':
            delta = timedelta(seconds=amount)
        elif unit == 'm':
            delta = timedelta(minutes=amount)
        elif unit == 'h':
            delta = timedelta(hours=amount)
        elif unit == 'd':
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
        event_type: Optional[EventType] = None,
        policy: Optional[PolicyDecision] = None,
        status: Optional[Status] = None,
        since: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Query audit logs with various filters.
        
        Args:
            tool: Filter by specific tool name
            resource: Filter by specific resource URI
            prompt: Filter by specific prompt name
            event_type: Filter by event type (tool, resource, prompt)
            policy: Filter by policy decision (allow, deny, warn, n/a)
            status: Filter by status (success, error)
            since: Time filter like '10m', '2h', '1d'
            limit: Maximum number of results to return
            
        Returns:
            List of log entries as dictionaries
        """
        conn = None
        try:
            # Open connection in read-only mode
            conn = duckdb.connect(str(self.db_path), read_only=True)
            
            # Build WHERE clause
            conditions = []
            params = []
            
            # Name-based filters (tool/resource/prompt)
            if tool:
                conditions.append("type = 'tool' AND name = ?")
                params.append(tool)
            elif resource:
                conditions.append("type = 'resource' AND name = ?")
                params.append(resource)
            elif prompt:
                conditions.append("type = 'prompt' AND name = ?")
                params.append(prompt)
            
            # Type filter
            if event_type:
                conditions.append("type = ?")
                params.append(event_type)
            
            # Policy filter
            if policy:
                conditions.append("policy_decision = ?")
                params.append(policy)
            
            # Status filter
            if status:
                conditions.append("status = ?")
                params.append(status)
            
            # Time filter
            if since:
                since_time = self._parse_since(since)
                conditions.append("timestamp >= ?")
                params.append(since_time)
            
            # Build query
            query = "SELECT * FROM logs"
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY timestamp DESC"
            query += f" LIMIT {limit}"
            
            # Execute query
            result = conn.execute(query, params).fetchall()
            
            # Get column names
            columns = [desc[0] for desc in conn.description]
            
            # Convert to list of dicts
            logs = []
            for row in result:
                log_entry = dict(zip(columns, row))
                # Convert timestamp to ISO format string
                if 'timestamp' in log_entry and log_entry['timestamp']:
                    log_entry['timestamp'] = log_entry['timestamp'].isoformat()
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
        **filter_kwargs
    ) -> int:
        """Export filtered logs to CSV file.
        
        Args:
            output_path: Path to write CSV file
            **filter_kwargs: Same filters as query_logs()
            
        Returns:
            Number of rows exported
        """
        conn = None
        try:
            # Get logs using the same filters but without limit
            filter_kwargs.pop('limit', None)  # Remove limit for export
            
            # Open connection in read-only mode
            conn = duckdb.connect(str(self.db_path), read_only=True)
            
            # Build WHERE clause (same logic as query_logs)
            conditions = []
            params = []
            
            if filter_kwargs.get('tool'):
                conditions.append("type = 'tool' AND name = ?")
                params.append(filter_kwargs['tool'])
            elif filter_kwargs.get('resource'):
                conditions.append("type = 'resource' AND name = ?")
                params.append(filter_kwargs['resource'])
            elif filter_kwargs.get('prompt'):
                conditions.append("type = 'prompt' AND name = ?")
                params.append(filter_kwargs['prompt'])
            
            if filter_kwargs.get('event_type'):
                conditions.append("type = ?")
                params.append(filter_kwargs['event_type'])
            
            if filter_kwargs.get('policy'):
                conditions.append("policy_decision = ?")
                params.append(filter_kwargs['policy'])
            
            if filter_kwargs.get('status'):
                conditions.append("status = ?")
                params.append(filter_kwargs['status'])
            
            if filter_kwargs.get('since'):
                since_time = self._parse_since(filter_kwargs['since'])
                conditions.append("timestamp >= ?")
                params.append(since_time)
            
            # Build query
            query = "SELECT * FROM logs"
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY timestamp DESC"
            
            # Export directly to CSV
            export_query = f"COPY ({query}) TO '{output_path}' (HEADER, DELIMITER ',')"
            result = conn.execute(export_query, params)
            
            # Get row count
            count_query = f"SELECT COUNT(*) FROM ({query})"
            row_count = conn.execute(count_query, params).fetchone()[0]
            
            return row_count
            
        except Exception as e:
            logger.error(f"Failed to export logs: {e}")
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
            conn = duckdb.connect(str(self.db_path), read_only=True)
            
            stats = {}
            
            # Total count
            stats['total_events'] = conn.execute("SELECT COUNT(*) FROM logs").fetchone()[0]
            
            # Count by type
            type_counts = conn.execute("""
                SELECT type, COUNT(*) as count 
                FROM logs 
                GROUP BY type
            """).fetchall()
            stats['by_type'] = {row[0]: row[1] for row in type_counts}
            
            # Count by status
            status_counts = conn.execute("""
                SELECT status, COUNT(*) as count 
                FROM logs 
                GROUP BY status
            """).fetchall()
            stats['by_status'] = {row[0]: row[1] for row in status_counts}
            
            # Count by policy decision
            policy_counts = conn.execute("""
                SELECT policy_decision, COUNT(*) as count 
                FROM logs 
                GROUP BY policy_decision
            """).fetchall()
            stats['by_policy'] = {row[0]: row[1] for row in policy_counts}
            
            # Time range
            time_range = conn.execute("""
                SELECT MIN(timestamp) as earliest, MAX(timestamp) as latest 
                FROM logs
            """).fetchone()
            
            if time_range[0] and time_range[1]:
                stats['earliest_event'] = time_range[0].isoformat()
                stats['latest_event'] = time_range[1].isoformat()
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get summary stats: {e}")
            raise
        finally:
            if conn:
                conn.close() 