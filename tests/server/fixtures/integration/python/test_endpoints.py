from typing import Dict, Any
from mxcp.runtime import config, on_init
from pydantic import BaseModel

global_var = None


@on_init
def setup_global_var():
    global global_var
    secret_params = config.get_secret("test_secret")
    global_var = secret_params.get("api_key") if secret_params else None


def check_secret() -> dict:
    """Check the current secret value."""
    secret_params = config.get_secret("test_secret")
    return {
        "api_key": secret_params.get("api_key") if secret_params else None,
        "endpoint": secret_params.get("endpoint") if secret_params else None,
        "has_secret": secret_params is not None,
    }


def echo_message(message: str) -> dict:
    """Echo a message back."""
    return {"original": message, "reversed": message[::-1], "length": len(message)}


def get_global_var() -> str:
    return global_var


def get_users_detailed() -> Dict[str, Any]:
    """Return an object with users array and count."""
    users = [
        {
            "id": 1,
            "name": "Alice Johnson",
            "email": "alice@example.com",
            "age": 28,
            "active": True,
            "roles": ["admin", "user"],
            "profile": {"department": "Engineering", "location": "San Francisco"},
        },
        {
            "id": 2,
            "name": "Bob Smith",
            "email": "bob@example.com",
            "age": 34,
            "active": False,
            "roles": ["user"],
            "profile": {"department": "Marketing", "location": "New York"},
        },
        {
            "id": 3,
            "name": "Carol Davis",
            "email": "carol@example.com",
            "age": 31,
            "active": True,
            "roles": ["manager", "user"],
            "profile": {"department": "Sales", "location": "Chicago"},
        },
    ]
    return {"users": users, "n": len(users)}


def get_users_simple() -> Dict[str, Any]:
    """Return an object with users array and count (same data, different type spec in .yml)."""
    users = [
        {
            "id": 1,
            "name": "Alice Johnson",
            "email": "alice@example.com",
            "age": 28,
            "active": True,
            "roles": ["admin", "user"],
            "profile": {"department": "Engineering", "location": "San Francisco"},
        },
        {
            "id": 2,
            "name": "Bob Smith",
            "email": "bob@example.com",
            "age": 34,
            "active": False,
            "roles": ["user"],
            "profile": {"department": "Marketing", "location": "New York"},
        },
        {
            "id": 3,
            "name": "Carol Davis",
            "email": "carol@example.com",
            "age": 31,
            "active": True,
            "roles": ["manager", "user"],
            "profile": {"department": "Sales", "location": "Chicago"},
        },
    ]
    return {"users": users, "n": len(users)}


def process_user_data(user_data: Dict[str, Any]) -> Dict[str, Any]:
    """Process a complex user data object and return analysis."""
    # Extract user info
    name = user_data.get("name", "Unknown")
    age = user_data.get("age", 0)
    preferences = user_data.get("preferences", {})
    contact = user_data.get("contact", {})

    # Perform some meaningful processing
    analysis = {
        "processed_name": name.upper(),
        "age_category": "adult" if age >= 18 else "minor",
        "has_email": bool(contact.get("email")),
        "has_phone": bool(contact.get("phone")),
        "preference_count": len(preferences.get("interests", [])),
        "is_premium": preferences.get("premium", False),
        "full_address": f"{contact.get('address', {}).get('street', '')}, {contact.get('address', {}).get('city', '')}, {contact.get('address', {}).get('country', '')}".strip(
            ", "
        ),
        "summary": f"{name} is a {age}-year-old {'premium' if preferences.get('premium') else 'regular'} user",
    }

    return {"original_data": user_data, "analysis": analysis, "processing_status": "success"}


# Pydantic models for testing
class UserProfile(BaseModel):
    """User profile model."""

    name: str
    age: int
    email: str
    is_premium: bool = False


class UserStats(BaseModel):
    """User statistics model."""

    total_users: int
    active_users: int
    premium_users: int
    average_age: float


def validate_user_profile(profile: UserProfile) -> str:
    """Take a pydantic model as parameter and return a primitive result."""
    # Validate and process the user profile
    if profile.age < 0:
        return "Invalid age: must be non-negative"

    if not profile.email or "@" not in profile.email:
        return "Invalid email format"

    status = "premium" if profile.is_premium else "regular"
    return f"User {profile.name} ({profile.age} years old, {profile.email}) is a {status} user - validation passed"


def get_user_stats(user_count: int) -> UserStats:
    """Take a primitive argument and return a pydantic model."""
    # Generate some mock statistics based on the user count
    active_ratio = 0.8
    premium_ratio = 0.3

    active_users = int(user_count * active_ratio)
    premium_users = int(user_count * premium_ratio)
    average_age = 32.5  # Mock average age

    return UserStats(
        total_users=user_count,
        active_users=active_users,
        premium_users=premium_users,
        average_age=average_age,
    )
