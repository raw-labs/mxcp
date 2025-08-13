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
            "profile": {
                "department": "Engineering",
                "location": "San Francisco"
            }
        },
        {
            "id": 2,
            "name": "Bob Smith",
            "email": "bob@example.com",
            "age": 34,
            "active": False,
            "roles": ["user"],
            "profile": {
                "department": "Marketing",
                "location": "New York"
            }
        },
        {
            "id": 3,
            "name": "Carol Davis",
            "email": "carol@example.com",
            "age": 31,
            "active": True,
            "roles": ["manager", "user"],
            "profile": {
                "department": "Sales",
                "location": "Chicago"
            }
        }
    ]
    return {
        "users": users,
        "n": len(users)
    }


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
            "profile": {
                "department": "Engineering",
                "location": "San Francisco"
            }
        },
        {
            "id": 2,
            "name": "Bob Smith",
            "email": "bob@example.com",
            "age": 34,
            "active": False,
            "roles": ["user"],
            "profile": {
                "department": "Marketing",
                "location": "New York"
            }
        },
        {
            "id": 3,
            "name": "Carol Davis",
            "email": "carol@example.com",
            "age": 31,
            "active": True,
            "roles": ["manager", "user"],
            "profile": {
                "department": "Sales",
                "location": "Chicago"
            }
        }
    ]
    return {
        "users": users,
        "n": len(users)
    }
