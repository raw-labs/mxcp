from datetime import datetime

from mxcp.server.services.audit.utils import map_legacy_query_params


def test_map_legacy_query_params_preserves_datetime_for_since() -> None:
    params = map_legacy_query_params(since="10m")

    assert "start_time" in params
    assert isinstance(params["start_time"], datetime)
