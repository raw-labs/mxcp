from mcp_server.server import MCPServer
from raw.endpoints.loader import list_all_endpoints

def run_server(session):
    # We will build an MCPServer dynamically based on endpoint YAML files
    endpoints = list_all_endpoints()

    # Placeholder logic - will dynamically register MCP tools/resources/prompts
    server = MCPServer()

    print(f"Loaded {len(endpoints)} endpoints from YAML definitions")
    print("Starting RAW MCP server (WIP)")

    # For now, just start empty server
    server.run()