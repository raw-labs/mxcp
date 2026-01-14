from typing import Any

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


def get_users_detailed() -> dict[str, Any]:
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


def get_users_simple() -> dict[str, Any]:
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


def process_user_data(user_data: dict[str, Any]) -> dict[str, Any]:
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


def count_item_keys(items: list[Any]) -> dict[str, Any]:
    """Count keys in each item after input validation/parsing.

    This is used as a regression test for `additionalProperties` handling: if extra
    keys are dropped during schema validation, the counts will be smaller than expected.
    """
    normalized: list[dict[str, Any]] = []
    for item in items:
        if hasattr(item, "model_dump"):
            normalized.append(item.model_dump())
        else:
            normalized.append(item)

    return {"counts": [len(obj) for obj in normalized]}


def count_item_keys_strict(items: list[Any]) -> dict[str, Any]:
    """Same behavior as `count_item_keys`, but used with a strict input schema."""
    return count_item_keys(items)


def check_optional_params(
    required_param: str,
    optional_param: str,
    optional_number: int,
    optional_float: float,
    optional_bool: bool,
    optional_date: str,
    optional_datetime: str,
) -> dict[str, Any]:
    """Function with various optional parameters of different types.
    Note: The parameter order in the .yml file is intentionally different from this function
    to test that parameter matching works correctly regardless of order.
    """
    return {
        "required_param": required_param,
        "optional_param": optional_param,
        "optional_number": optional_number,
        "optional_float": optional_float,
        "optional_bool": optional_bool,
        "optional_date": optional_date,
        "optional_datetime": optional_datetime,
    }
