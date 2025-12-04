"""Python file with function parameters that don't match YAML definition."""


def get_user_info(user_id: int) -> dict:
    """Function expects user_id, but YAML will define different parameters."""
    return {"user_id": user_id, "name": "test_user"}
