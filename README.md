# MCP Agent Orchestrator

A Python service that connects an LLM to tools exposed by one or more Model Context Protocol (MCP) servers. It discovers tools at runtime, lets the model choose tools, executes calls through MCP sessions, and records an execution trace.

## Features

- Discover tools from configured MCP servers
- Convert MCP tool definitions into LLM function tools
- Execute multi-step tool calls with a configurable round limit
- Record tool arguments, results and errors
- Expose execution and tool discovery through FastAPI
- Include a small calculator MCP server for local testing

## Architecture

1. The API receives a user task at `POST /run`.
2. The orchestrator starts the configured MCP server processes and initializes client sessions.
3. It discovers available tools and provides their schemas to the LLM.
4. The LLM can request one or more tool calls.
5. The orchestrator validates the arguments, invokes the corresponding MCP tools and adds their results to the conversation.
6. The LLM produces a final response. The API returns that response with the execution trace.

## Requirements

- Python 3.11 or newer
- An OpenAI API key
- Network access for the LLM API
- Any MCP servers you configure

## Setup

```bash
git clone https://github.com/truly-vivek/mcp-agent-orchestrator.git
cd mcp-agent-orchestrator

python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set your API key:

```env
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4o-mini
MAX_TOOL_ROUNDS=6
MCP_SERVERS_JSON=[{"name":"calculator","command":"python","args":["examples/calculator_server.py"],"env":{},"cwd":"."}]
```

The server configuration is a JSON array. Each entry contains a unique `name`, executable `command`, optional `args`, optional environment variables and optional working directory. The example launches the included calculator server using the current Python environment.

On Windows, use the Python executable path in `command` if the `python` command is not available to the process running the API.

## Run

```bash
uvicorn app.main:app --reload
```

Open the interactive API documentation at [http://localhost:8000/docs](http://localhost:8000/docs).

## API

### Health check

`GET /health`

### Discover connected tools

`GET /tools`

Returns the configured MCP tools and their input schemas.

### Run an agent task

`POST /run`

Example request:

```json
{
  "prompt": "Use the calculator tools to multiply 12 by 8, then add 5 to the result."
}
```

The response contains the final answer, a trace of tool calls and the number of tool-call rounds.

## Tests

```bash
pytest -q
```

The tests cover API health and request validation, tool-name normalization and MCP result serialization. They do not replace an end-to-end test with a real LLM API key and running MCP server.

## Configuration and security notes

- Keep API keys in environment variables; never commit `.env`.
- Only configure MCP servers and executable commands that you trust. A stdio MCP server runs as a local subprocess with the permissions of the API process.
- Review third-party tool descriptions and schemas before connecting them.
- Tool-call limits are configurable to prevent unbounded agent loops.
- This is a development project. Add authentication, authorization, rate limiting, request isolation, audit retention policies and deployment hardening before exposing it to untrusted users.

## Project structure

```text
app/
  config.py
  main.py
  orchestrator.py
examples/
  calculator_server.py
tests/
  test_api.py
  test_orchestrator.py
```
