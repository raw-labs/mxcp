from utils.models import Parameter
from lsprotocol import types
from pygls.server import LanguageServer
from utils.duckdb_connector import DuckDBConnector
from features.completion.completion import register_completion


def test_span(yaml_manager_inlined):
    span = yaml_manager_inlined.code_span
    assert span is not None, "Offset should not be None"
    assert isinstance(span, tuple), "Offset should be a tuple"
    start = span[0]
    end = span[1]
    assert isinstance(start, types.Position), "Start should be a Position"
    assert isinstance(end, types.Position), "End should be a Position"
    assert start.line == 17, "Expected start line to be 17, got {}".format(start.line)
    assert start.character == 6, "Expected start character to be 6, got {}".format(
        start.character
    )
    assert end.line == 41, "Expected end line to be 41, got {}".format(end.line)
    assert end.character == 30, "Expected end character to be 30, got {}".format(
        end.character
    )


def test_should_complete(yaml_manager_inlined):
    should_parse = yaml_manager_inlined.should_provide_lsp(types.Position(28, 10))
    assert should_parse is True, "Expected should_provide_completion to be True"


def test_should_not_complete(yaml_manager_empty, yaml_manager_inlined):
    should_parse = yaml_manager_empty.should_provide_lsp(types.Position(28, 10))
    assert should_parse is False, "Expected should_provide_completion to be False"
    should_parse = yaml_manager_inlined.should_provide_lsp(types.Position(0, 0))
    assert should_parse is False, "Expected should_provide_completion to be False"


def test_simple_completion(duckdb_connector, yaml_manager_inlined):
    completions = duckdb_connector.get_completions(
        "select * from ", parameters=yaml_manager_inlined.get_parameters()
    )
    assert completions is not None, "Completions should not be None"
    assert isinstance(
        completions, types.CompletionList
    ), "Completions should be a CompletionList"
    assert len(completions.items) > 0, "Completions should not be empty"
    assert any(
        item.label == "min_magnitude" for item in completions.items
    ), "'min_magnitude' should be in completion items"


def test_completion(duckdb_connector, yaml_manager_inlined):
    completions = duckdb_connector.get_completions(
        """      
      WITH raw AS (
        SELECT * FROM read_json_auto('https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson')
      ),
      features AS (
        SELECT
          feature
        FROM raw,
            UNNEST(features) AS feature
      ),
      quakes AS (
        SELECT
          feature -> 'unnest' -> 'properties' -> 'mag' AS magnitude,
          feature -> 'unnest' -> 'properties' -> 'place' AS location,
          feature -> 'unnest' -> 'properties' -> 'time' AS time,
          feature -> 'unnest' -> 'geometry' -> 'coordinates' AS coords
        FROM features
      )
      SELECT
        CAST(magnitude AS DOUBLE) AS magnitude,
        location,
        CAST(time AS BIGINT) AS time,
        coords
      FROM quakes
      WHERE CAST(magnitude AS DOUBLE) >= $min_magnitude
      ORDER BY magnitude DESC;
      """,
        parameters=yaml_manager_inlined.get_parameters(),
    )
    assert completions is not None, "Completions should not be None"
    assert isinstance(
        completions, types.CompletionList
    ), "Completions should be a CompletionList"
    assert len(completions.items) > 0, "Completions should not be empty"
    assert any(
        item.label == "min_magnitude" for item in completions.items
    ), "'min_magnitude' should be in completion items"

