from typing import List, Dict, Optional
from pydantic import BaseModel


class User(BaseModel):
    """Simple user model for testing container types."""

    name: str
    age: int
    email: str


def process_user_list(users: List[User]) -> dict:
    """Test function that takes a list of pydantic models."""
    total_age = sum(user.age for user in users)
    avg_age = total_age / len(users) if users else 0
    names = [user.name for user in users]

    return {
        "user_count": len(users),
        "average_age": avg_age,
        "names": names,
        "total_age": total_age,
    }


def process_user_dict(user_map: Dict[str, User]) -> dict:
    """Test function that takes a dict of pydantic models."""
    user_count = len(user_map)
    names = list(user_map.keys())
    ages = [user.age for user in user_map.values()]
    avg_age = sum(ages) / len(ages) if ages else 0

    return {
        "user_count": user_count,
        "user_keys": sorted(names),
        "average_age": avg_age,
        "oldest_user": max(user_map.values(), key=lambda u: u.age).name if user_map else None,
    }


def process_optional_user(user: Optional[User] = None) -> dict:
    """Test function with optional pydantic model."""
    if user is None:
        return {"has_user": False, "message": "No user provided"}

    return {
        "has_user": True,
        "user_name": user.name,
        "user_age": user.age,
        "user_email": user.email,
    }


# Test functions using built-in container types (Python 3.9+)
def process_builtin_user_list(users: list[User]) -> dict:
    """Test function using built-in list[User] (Python 3.9+)."""
    total_age = sum(user.age for user in users)
    avg_age = total_age / len(users) if users else 0
    names = [user.name for user in users]

    return {
        "user_count": len(users),
        "average_age": avg_age,
        "names": names,
        "total_age": total_age,
        "type_used": "builtin_list",
    }


def process_builtin_user_dict(user_map: dict[str, User]) -> dict:
    """Test function using built-in dict[str, User] (Python 3.9+)."""
    user_count = len(user_map)
    names = list(user_map.keys())
    ages = [user.age for user in user_map.values()]
    avg_age = sum(ages) / len(ages) if ages else 0

    return {
        "user_count": user_count,
        "user_keys": sorted(names),
        "average_age": avg_age,
        "oldest_user": max(user_map.values(), key=lambda u: u.age).name if user_map else None,
        "type_used": "builtin_dict",
    }
