from mxcp.plugins import MXCPBasePlugin
from typing import Dict
import duckdb
from duckdb.typing import *

def func_hello_world():
  return "Hello, World!"

class MXCPPlugin(MXCPBasePlugin):

  def __init__(self, name: str, config: Dict[str, str], conn: duckdb.DuckDBPyConnection):
    super().__init__(name, config, conn)
    # Register a function in the plugin
    conn.create_function("hello_world", func_hello_world, [], VARCHAR)
