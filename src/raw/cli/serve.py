import click
from typing import Dict, Any, Optional
from raw.endpoints.executor import execute_endpoint, EndpointType
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="RAW Endpoints")

class EndpointRequest(BaseModel):
    params: Dict[str, Any] = {}

@app.post("/{endpoint_type}/{name}")
async def run_endpoint(endpoint_type: str, name: str, request: EndpointRequest):
    try:
        result = execute_endpoint(endpoint_type, name, request.params)
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@click.command(name="serve")
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", default=8000, help="Port to bind to")
@click.option("--profile", help="Profile name to use")
def serve_endpoints(host: str, port: int, profile: Optional[str]):
    """Start a server for running endpoints"""
    click.echo(f"Starting server at http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)