"""
Google Calendar MCP client implementation using mxcp OAuth authentication.

This module provides Google Calendar API integration with:
- OAuth 2.0 authentication via mxcp framework
- Thread-safe client caching for performance
- Simplified time handling for LLM consumption
- Comprehensive error handling and user-friendly messages
- Full type safety with Pydantic models
"""

# Required for union syntax (|) in type annotations with runtime objects like threading.Lock
# Without this, Python tries to evaluate "threading.Lock | None" at runtime, which fails
from __future__ import annotations

import logging
import threading
from datetime import date, datetime, timezone
from functools import wraps
from typing import Any

from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource, build  # type: ignore[import-untyped]
from googleapiclient.errors import HttpError  # type: ignore[import-untyped]

from mxcp.runtime import on_init, on_shutdown
from mxcp.sdk.auth.context import get_user_context

# =============================================================================
# TIME CONVERSION UTILITIES
# =============================================================================


def _datetime_to_google_time(
    dt: datetime, all_day: bool = False, time_zone: str | None = None
) -> dict[str, Any]:
    """
    Convert datetime object to Google Calendar API time format.

    Args:
        dt: Python datetime object (should be timezone-aware)
        all_day: Whether this represents an all-day event
        time_zone: Optional timezone override

    Returns:
        Google API time object: {"dateTime": "...", "timeZone": "..."}
        or {"date": "YYYY-MM-DD"} for all-day events
    """
    if all_day:
        # For all-day events, use date format
        return {"date": dt.date().isoformat()}
    else:
        # For timed events, use dateTime format
        time_obj = {"dateTime": dt.isoformat()}

        # Add timezone if specified or if datetime has timezone info
        if time_zone:
            time_obj["timeZone"] = time_zone
        elif dt.tzinfo:
            # Extract timezone name from datetime object if possible
            tz_name = getattr(dt.tzinfo, "zone", None) or str(dt.tzinfo)
            if tz_name != "UTC" and "+" not in tz_name and "-" not in tz_name:
                time_obj["timeZone"] = tz_name
        else:
            # If no timezone info is available, try to get user's timezone
            try:
                user_timezone = _get_user_timezone()
                logger.warning(
                    f"Datetime object has no timezone info, using user timezone: {user_timezone}"
                )
                time_obj["timeZone"] = user_timezone
            except ValueError as e:
                raise ValueError(
                    f"Datetime object has no timezone information and cannot determine timezone from calendar. "
                    f"Please either: 1) Use timezone-aware datetime objects, or 2) Specify the time_zone parameter. "
                    f"Original error: {e}"
                ) from e

        return time_obj


def _get_user_timezone() -> str:
    """Get the user's timezone from their primary calendar.

    This function only tries to get the timezone from the user's primary calendar.
    If that fails, it raises an exception to force explicit timezone specification.

    Results are cached to avoid repeated lookups.

    Returns:
        IANA timezone identifier from user's primary calendar

    Raises:
        ValueError: If timezone cannot be determined from primary calendar
    """
    global _user_timezone_cache, _timezone_cache_lock

    # Check cache first
    if _timezone_cache_lock and _user_timezone_cache:
        with _timezone_cache_lock:
            if _user_timezone_cache:
                return _user_timezone_cache

    try:
        # Get timezone from user's primary calendar
        calendar_info = get_calendar("primary")
        if calendar_info and calendar_info.get("timeZone"):
            user_timezone: str = calendar_info["timeZone"]
            logger.debug(f"Using timezone from primary calendar: {user_timezone}")
            # Cache the result
            if _timezone_cache_lock:
                with _timezone_cache_lock:
                    _user_timezone_cache = user_timezone
            return user_timezone
        else:
            raise ValueError("Primary calendar does not have timezone information")

    except Exception as e:
        logger.debug(f"Could not get timezone from primary calendar: {e}")
        raise ValueError(
            "Cannot determine timezone from primary calendar. "
            "Please specify the time_zone parameter explicitly in your function call."
        ) from e


def _google_time_to_datetime(google_time: dict[str, Any]) -> tuple[datetime, bool]:
    """
    Convert Google Calendar API time format to datetime object.

    Args:
        google_time: Google API time object

    Returns:
        Tuple of (datetime_object, is_all_day)
    """
    if "date" in google_time:
        # All-day event - convert date to datetime at midnight UTC
        date_obj = date.fromisoformat(google_time["date"])
        dt = datetime.combine(date_obj, datetime.min.time(), tzinfo=timezone.utc)
        return dt, True
    elif "dateTime" in google_time:
        # Timed event - parse ISO datetime
        dt = datetime.fromisoformat(google_time["dateTime"])
        return dt, False
    else:
        raise ValueError(f"Invalid Google time format: {google_time}")


def _convert_event_to_simplified(google_event: dict[str, Any]) -> dict[str, Any]:
    """
    Convert Google Calendar API event to our simplified EventInfo format.

    Args:
        google_event: Raw event from Google Calendar API

    Returns:
        Event in simplified format matching EventInfo model
    """
    # Convert start/end times
    start_dt, start_all_day = _google_time_to_datetime(google_event["start"])
    end_dt, end_all_day = _google_time_to_datetime(google_event["end"])

    # Ensure both times have same all-day status
    all_day = start_all_day and end_all_day

    simplified_event = {
        "id": google_event["id"],
        "summary": google_event.get("summary", ""),
        "description": google_event.get("description"),
        "location": google_event.get("location"),
        "start_time": start_dt,
        "end_time": end_dt,
        "all_day": all_day,
        "time_zone": google_event.get("start", {}).get("timeZone"),
        "status": google_event.get("status", "confirmed"),
        "htmlLink": google_event.get("htmlLink", ""),
        "created": datetime.fromisoformat(google_event["created"].replace("Z", "+00:00")),
        "updated": datetime.fromisoformat(google_event["updated"].replace("Z", "+00:00")),
        "calendar_id": google_event.get("calendarId", "unknown"),  # Added by our code
        "etag": google_event.get("etag"),
    }

    # Convert attendees if present
    if "attendees" in google_event:
        simplified_event["attendees"] = [
            {
                "email": att["email"],
                "displayName": att.get("displayName"),
                "responseStatus": att.get("responseStatus", "needsAction"),
                "optional": att.get("optional", False),
                "resource": att.get("resource", False),
                "comment": att.get("comment"),
                "additionalGuests": att.get("additionalGuests", 0),
            }
            for att in google_event["attendees"]
        ]

    # Convert creator/organizer if present
    for role in ["creator", "organizer"]:
        if role in google_event:
            simplified_event[role] = {
                "email": google_event[role].get("email"),
                "displayName": google_event[role].get("displayName"),
                "self": google_event[role].get("self", False),
            }

    # Handle recurrence rules
    if "recurrence" in google_event:
        simplified_event["recurrence"] = google_event["recurrence"]

    # Handle reminders
    if "reminders" in google_event:
        reminders = google_event["reminders"]
        simplified_event["reminders"] = {
            "useDefault": reminders.get("useDefault", True),
            "overrides": reminders.get("overrides"),
        }

    # Handle transparency and visibility
    simplified_event["transparency"] = google_event.get("transparency", "opaque")
    simplified_event["visibility"] = google_event.get("visibility", "default")

    return simplified_event


def _convert_simplified_to_google_event(simplified_event: dict[str, Any]) -> dict[str, Any]:
    """
    Convert simplified event format to Google Calendar API format.

    Args:
        simplified_event: Event in our simplified format

    Returns:
        Event in Google Calendar API format
    """
    google_event = {
        "summary": simplified_event["summary"],
        "start": _datetime_to_google_time(
            simplified_event["start_time"],
            simplified_event.get("all_day", False),
            simplified_event.get("time_zone"),
        ),
        "end": _datetime_to_google_time(
            simplified_event["end_time"],
            simplified_event.get("all_day", False),
            simplified_event.get("time_zone"),
        ),
    }

    # Add optional fields
    optional_fields = ["description", "location"]
    for field in optional_fields:
        if field in simplified_event and simplified_event[field] is not None:
            google_event[field] = simplified_event[field]

    # Convert attendees
    if "attendees" in simplified_event and simplified_event["attendees"]:
        google_event["attendees"] = [
            (
                {"email": str(email)}
                if isinstance(email, str)
                else {
                    "email": (
                        str(email) if isinstance(email, str) else str(attendee.get("email", ""))
                    ),
                    "displayName": attendee.get("displayName"),
                    "optional": attendee.get("optional", False),
                    "resource": attendee.get("resource", False),
                    "comment": attendee.get("comment"),
                    "additionalGuests": attendee.get("additionalGuests", 0),
                }
            )
            for email in simplified_event["attendees"]
            for attendee in [email if isinstance(email, dict) else {"email": email}]
        ]

    # Add transparency and visibility if specified
    if "transparency" in simplified_event:
        google_event["transparency"] = simplified_event["transparency"]
    if "visibility" in simplified_event:
        google_event["visibility"] = simplified_event["visibility"]
    if "recurrence" in simplified_event:
        google_event["recurrence"] = simplified_event["recurrence"]

    # Add reminders if specified
    if "reminders" in simplified_event and simplified_event["reminders"]:
        google_event["reminders"] = simplified_event["reminders"]

    return google_event


# =============================================================================
# THREAD-SAFE CLIENT CACHING
# =============================================================================

# Thread-safe cache for Google Calendar service clients
_client_cache: dict[str, Resource] | None = None
_cache_lock: threading.Lock | None = None

# Global timezone cache to avoid repeated lookups
_user_timezone_cache: str | None = None
_timezone_cache_lock: threading.Lock | None = None


@on_init
def init_client_cache() -> None:
    """Initialize the Google Calendar client cache and timezone cache."""
    global _client_cache, _cache_lock, _timezone_cache_lock
    _client_cache = {}
    _cache_lock = threading.Lock()
    _timezone_cache_lock = threading.Lock()


@on_shutdown
def clear_client_cache() -> None:
    """Clear the Google Calendar client cache and timezone cache."""
    global _client_cache, _cache_lock, _user_timezone_cache, _timezone_cache_lock
    _client_cache = None
    _cache_lock = None
    _user_timezone_cache = None
    _timezone_cache_lock = None


def _get_cache_key(context: Any) -> str | None:
    """Generate cache key based on user context."""
    if not context:
        return None

    # Use user ID as cache key for per-user client isolation
    user_id = getattr(context, "user_id", None) or getattr(context, "id", None)
    if user_id:
        return f"gcal:{user_id}"

    return None


def _get_google_credentials() -> Credentials:
    """Get Google OAuth credentials from mxcp user context."""
    context = get_user_context()
    if not context or not context.external_token:
        raise ValueError("No user context available. User must be authenticated.")

    # Create Google credentials object with OAuth token
    credentials = Credentials(token=context.external_token)  # type: ignore[no-untyped-call]
    return credentials


# =============================================================================
# LOGGING & ERROR HANDLING
# =============================================================================

# Set up comprehensive logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def with_session_retry(func: Any) -> Any:
    """
    Decorator for handling OAuth token refresh and API errors with user-friendly messages.

    Wraps functions to automatically handle:
    - OAuth token refresh failures (RefreshError)
    - Google API HTTP errors with specific status codes
    - Client cache invalidation on auth failures
    - Comprehensive error logging for debugging
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            logger.info(f"Executing {func.__name__} with args={args}, kwargs={kwargs}")
            result = func(*args, **kwargs)
            logger.info(f"Successfully completed {func.__name__}")
            return result

        except RefreshError as e:
            # OAuth token has expired and cannot be refreshed
            logger.warning(f"OAuth token refresh failed in {func.__name__}: {e}")
            clear_client_cache()  # Clear cache to force re-authentication
            error_msg = (
                "Your Google Calendar access has expired. Please re-authenticate to continue."
            )
            logger.error(f"Authentication error: {error_msg}")
            raise ValueError(error_msg) from e

        except HttpError as e:
            # Handle specific Google API errors with detailed logging
            status = e.resp.status
            error_details = str(e)
            logger.error(
                f"Google API HttpError in {func.__name__}: status={status}, details={error_details}"
            )

            # Clear cache on authentication errors
            if status in [401, 403]:
                context = get_user_context()
                cache_key = _get_cache_key(context)
                if cache_key and _cache_lock and _client_cache:
                    with _cache_lock:
                        _client_cache.pop(cache_key, None)

            # Just forward the original Google API error - it's already clear and actionable
            raise ValueError(f"Google Calendar API error: {error_details}") from e

        # ValidationError removed since we no longer use Pydantic models

        except ValueError as e:
            # Re-raise ValueError (these are user-friendly messages)
            logger.warning(f"User error in {func.__name__}: {e}")
            raise

        except Exception as e:
            # Catch-all for unexpected errors
            logger.error(
                f"Unexpected error in {func.__name__}: {type(e).__name__}: {e}", exc_info=True
            )
            raise ValueError(f"An unexpected error occurred: {str(e)}") from e

    return wrapper


def _get_google_calendar_client() -> Resource:
    """
    Get cached Google Calendar API client or create new one with OAuth authentication.

    Uses per-user caching for performance and proper multi-user isolation.
    """
    try:
        # Get authenticated user context
        context = get_user_context()
        if not context:
            raise ValueError("No user context available. User must be authenticated.")

        # Check cache first
        cache_key = _get_cache_key(context)
        if cache_key and _cache_lock and _client_cache:
            with _cache_lock:
                if cache_key in _client_cache:
                    logging.info("Using cached Google Calendar client")
                    return _client_cache[cache_key]

        logging.info("Creating new Google Calendar client")
        # Create new authenticated client
        credentials = _get_google_credentials()
        service = build(
            serviceName="calendar",
            version="v3",
            credentials=credentials,
            cache_discovery=True,  # Cache API discovery documents
            num_retries=3,  # Retry transient failures
        )

        # Cache the client for this user
        if cache_key and _cache_lock and _client_cache:
            with _cache_lock:
                _client_cache[cache_key] = service

        return service

    except Exception as e:
        raise ValueError(f"Failed to initialize Google Calendar client: {str(e)}") from e


# =============================================================================
# MCP TOOL FUNCTIONS
# =============================================================================


@with_session_retry
def whoami() -> dict[str, Any]:
    """
    Get information about the currently authenticated user.

    Returns:
        UserInfo object with user profile data from Google OAuth

    Note:
        Uses OAuth profile information, no additional API calls required
    """
    context = get_user_context()
    if not context:
        raise ValueError("No user context available. User must be authenticated.")

    # Extract user information from OAuth profile
    raw_profile = context.raw_profile or {}

    # Return plain dictionary following standard MXCP pattern
    return {
        "id": raw_profile.get("sub") or raw_profile.get("id", "unknown"),
        "email": raw_profile.get("email", "unknown@example.com"),
        "name": raw_profile.get("name", "Unknown User"),
        "given_name": raw_profile.get("given_name"),
        "family_name": raw_profile.get("family_name"),
        "picture": raw_profile.get("picture"),
        "locale": raw_profile.get("locale"),
        "verified_email": raw_profile.get("email_verified"),
    }


@with_session_retry
def list_calendars(
    show_hidden: bool = False,
    show_deleted: bool = False,
    max_results: int = 100,
    min_access_role: str | None = None,
) -> list[dict[str, Any]]:
    """
    List all calendars accessible to the authenticated user.

    Args:
        show_hidden: Include hidden calendars in results
        show_deleted: Include deleted calendars in results
        max_results: Maximum number of calendars to return (1-250)
        min_access_role: Filter by minimum access level

    Returns:
        List of CalendarInfo objects with user's accessible calendars

    Raises:
        ValueError: If user is not authenticated or parameters are invalid
    """
    service = _get_google_calendar_client()

    # Build parameters
    params: dict[str, Any] = {
        "maxResults": min(max_results, 250),
        "showHidden": show_hidden,
        "showDeleted": show_deleted,
    }

    if min_access_role:
        params["minAccessRole"] = min_access_role

    # Execute API call
    result = service.calendarList().list(**params).execute()

    # Return plain dictionaries following standard MXCP pattern
    calendars = []
    for cal in result.get("items", []):
        calendar_dict = {
            "id": cal["id"],
            "summary": cal.get("summary", ""),
            "description": cal.get("description"),
            "timeZone": cal.get("timeZone", "UTC"),
            "accessRole": cal.get("accessRole", "reader"),
            "primary": cal.get("primary", False),
            "backgroundColor": cal.get("backgroundColor"),
            "foregroundColor": cal.get("foregroundColor"),
            "selected": cal.get("selected", False),
            "hidden": cal.get("hidden", False),
            "defaultReminders": cal.get("defaultReminders"),
        }
        calendars.append(calendar_dict)

    return calendars


@with_session_retry
def get_calendar(calendar_id: str) -> dict[str, Any]:
    """
    Get detailed information for a specific calendar.

    Args:
        calendar_id: Calendar identifier or 'primary' for main calendar

    Returns:
        CalendarInfo object with calendar details

    Raises:
        ValueError: If calendar_id is invalid or user lacks access
    """
    service = _get_google_calendar_client()

    try:
        result = service.calendarList().get(calendarId=calendar_id).execute()
    except HttpError as e:
        if e.resp.status == 404:
            raise ValueError(
                f"Calendar '{calendar_id}' not found or you don't have access to it"
            ) from e
        raise

    # Return plain dictionary following standard MXCP pattern
    return {
        "id": result["id"],
        "summary": result.get("summary", ""),
        "description": result.get("description"),
        "timeZone": result.get("timeZone", "UTC"),
        "accessRole": result.get("accessRole", "reader"),
        "primary": result.get("primary", False),
        "backgroundColor": result.get("backgroundColor"),
        "foregroundColor": result.get("foregroundColor"),
        "selected": result.get("selected", False),
        "hidden": result.get("hidden", False),
        "defaultReminders": result.get("defaultReminders"),
    }


@with_session_retry
def list_events(
    calendar_id: str = "primary",
    time_min: datetime | None = None,
    time_max: datetime | None = None,
    max_results: int = 250,
    single_events: bool = True,
    order_by: str = "startTime",
    page_token: str | None = None,
) -> dict[str, Any]:
    """
    List events from a specific calendar with optional time filtering.

    Args:
        calendar_id: Calendar to query ('primary' or specific calendar ID)
        time_min: Lower bound for event start times (inclusive)
        time_max: Upper bound for event start times (exclusive)
        max_results: Maximum number of events to return (1-2500)
        single_events: Whether to expand recurring events into instances
        order_by: Sort order - 'startTime' or 'updated'
        page_token: Token for pagination

    Returns:
        EventSearchResult with events and pagination info
    """
    service = _get_google_calendar_client()

    # Build parameters
    params = {
        "calendarId": calendar_id,
        "maxResults": min(max_results, 2500),
        "singleEvents": single_events,
        "orderBy": order_by,
    }

    if time_min:
        params["timeMin"] = time_min.isoformat()
    if time_max:
        params["timeMax"] = time_max.isoformat()
    if page_token:
        params["pageToken"] = page_token

    # Execute API call
    result = service.events().list(**params).execute()

    # Convert events to simplified format
    events = []
    for event in result.get("items", []):
        event["calendarId"] = calendar_id  # Add calendar_id to event
        simplified_event = _convert_event_to_simplified(event)
        events.append(simplified_event)

    # Return plain dictionary following standard MXCP pattern
    return {
        "events": events,
        "next_page_token": result.get("nextPageToken"),
        "total_results": len(events),
    }


@with_session_retry
def get_event(calendar_id: str, event_id: str) -> dict[str, Any]:
    """
    Retrieve detailed information for a specific event.

    Args:
        calendar_id: Calendar containing the event
        event_id: Event identifier

    Returns:
        EventInfo object with complete event details

    Raises:
        ValueError: If event not found or user lacks access
    """
    service = _get_google_calendar_client()

    try:
        result = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
    except HttpError as e:
        if e.resp.status == 404:
            raise ValueError(f"Event '{event_id}' not found in calendar '{calendar_id}'") from e
        raise

    # Add calendar_id to event
    result["calendarId"] = calendar_id
    simplified_event = _convert_event_to_simplified(result)

    return simplified_event


@with_session_retry
def search_events(
    q: str,
    calendar_id: str = "primary",
    time_min: datetime | None = None,
    time_max: datetime | None = None,
    max_results: int = 250,
    page_token: str | None = None,
) -> dict[str, Any]:
    """
    Search for events matching a text query.

    Args:
        q: Free text search query (searches title, description, location, attendees)
        calendar_id: Calendar to search ('primary' or specific calendar ID)
        time_min: Earliest event start time to include
        time_max: Latest event start time to include
        max_results: Maximum number of events to return
        page_token: Token for pagination

    Returns:
        EventSearchResult with matching events and pagination info
    """
    service = _get_google_calendar_client()

    # Build parameters
    params = {
        "calendarId": calendar_id,
        "q": q,
        "maxResults": min(max_results, 2500),
        "singleEvents": True,
        "orderBy": "startTime",
    }

    if time_min:
        params["timeMin"] = time_min.isoformat()
    if time_max:
        params["timeMax"] = time_max.isoformat()
    if page_token:
        params["pageToken"] = page_token

    # Execute API call
    result = service.events().list(**params).execute()

    # Convert events to simplified format
    events = []
    for event in result.get("items", []):
        event["calendarId"] = calendar_id  # Add calendar_id to event
        simplified_event = _convert_event_to_simplified(event)
        events.append(simplified_event)

    # Return plain dictionary following standard MXCP pattern
    return {
        "events": events,
        "next_page_token": result.get("nextPageToken"),
        "total_results": len(events),
    }


@with_session_retry
def get_freebusy(calendar_ids: list[str], time_min: datetime, time_max: datetime) -> dict[str, Any]:
    """
    Check free/busy status across multiple calendars.

    Args:
        calendar_ids: List of calendar IDs to check (use 'primary' for main calendar)
        time_min: Start time for availability check
        time_max: End time for availability check

    Returns:
        FreeBusyResponse with busy periods for each calendar

    Note:
        Useful for finding meeting slots and checking availability before scheduling
    """
    if time_min >= time_max:
        raise ValueError("time_max must be after time_min")

    service = _get_google_calendar_client()

    # Build request
    request_body = {
        "timeMin": time_min.isoformat(),
        "timeMax": time_max.isoformat(),
        "items": [{"id": cal_id} for cal_id in calendar_ids],
    }

    # Execute API call
    result = service.freebusy().query(body=request_body).execute()

    # Convert to plain dictionary format following standard MXCP pattern
    calendars = []
    for calendar_id in calendar_ids:
        calendar_data = result.get("calendars", {}).get(calendar_id, {})

        # Convert busy times to plain dictionaries
        busy_times = []
        for busy_period in calendar_data.get("busy", []):
            busy_times.append(
                {
                    "start": busy_period["start"],
                    "end": busy_period["end"],
                }
            )

        calendars.append(
            {"calendar_id": calendar_id, "busy": busy_times, "errors": calendar_data.get("errors")}
        )

    return {
        "time_min": time_min.isoformat(),
        "time_max": time_max.isoformat(),
        "calendars": calendars,
    }
