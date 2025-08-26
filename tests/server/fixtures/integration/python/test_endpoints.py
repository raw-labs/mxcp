from typing import Dict, Any
from mxcp.runtime import config, on_init

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


def check_integer_parameter(top_n: int) -> Dict[str, Any]:
    """Test function that expects an integer parameter and fails if it gets a float.
    
    This function reproduces the bug where JSON float values like 0.0 are not
    converted to integers before being passed to Python functions.
    """
    # Log the actual type and value received for debugging
    actual_type = type(top_n)
    
    # This assertion should pass if type conversion is working correctly
    # If this fails, it means the bug exists - float values are not being converted to int
    if not isinstance(top_n, int):
        return {
            "top_n": top_n,
            "type_received": str(actual_type),
            "selected_items": [],
            "test_passed": False,
            "error": f"Expected int, got {actual_type}: {top_n}"
        }
    
    # Use the parameter as an array index to demonstrate why integers are needed
    test_array = ["first", "second", "third", "fourth", "fifth"]
    
    # This would fail with a float even if it's 0.0
    if top_n < 0 or top_n >= len(test_array):
        selected_items = []
    else:
        selected_items = test_array[:top_n] if top_n > 0 else []
    
    return {
        "top_n": top_n,
        "type_received": str(actual_type),
        "selected_items": selected_items,
        "test_passed": True
    }
