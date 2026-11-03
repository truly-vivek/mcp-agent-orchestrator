from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.orchestrator import MCPAgentOrchestrator


class RunRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=12000)


class ToolTrace(BaseModel):
    tool: str
    arguments: Any
    result: str
    is_error: bool


class RunResponse(BaseModel):
    answer: str
    trace: list[ToolTrace]
    tool_rounds: int


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.orchestrator = MCPAgentOrchestrator(settings)
    yield


app = FastAPI(
    title="MCP Agent Orchestrator",
    description="An API for coordinating LLM reasoning with tools exposed by MCP servers.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/tools")
async def list_tools() -> dict[str, list[dict[str, Any]]]:
    try:
        tools = await app.state.orchestrator.list_available_tools()
        return {"tools": tools}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not load MCP tools: {exc}") from exc


@app.post("/run", response_model=RunResponse)
async def run_agent(request: RunRequest) -> RunResponse:
    try:
        result = await app.state.orchestrator.run(request.prompt)
        return RunResponse(**result)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Agent execution failed: {exc}") from exc
