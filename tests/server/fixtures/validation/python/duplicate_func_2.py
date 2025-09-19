"""Second Python file with duplicate function name."""


def get_data(param2: int) -> dict:
    """Function in second file - same name but different signature."""
    return {"source": "file2", "param2": param2}
