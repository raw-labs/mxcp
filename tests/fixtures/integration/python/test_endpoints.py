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
        "has_secret": secret_params is not None
    }

def echo_message(message: str) -> dict:
    """Echo a message back."""
    return {
        "original": message,
        "reversed": message[::-1],
        "length": len(message)
    } 

def get_global_var() -> str:
    return global_var