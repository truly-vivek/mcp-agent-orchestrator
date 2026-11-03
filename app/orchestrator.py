import json
import re
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import AsyncOpenAI

from app.config import MCPServerConfig, Settings


SYSTEM_PROMPT = """You are a practical assistant that can use tools exposed by connected MCP servers.
Use tools when they help complete the user's request. Do not claim a tool action succeeded
unless its result confirms success. Explain uncertainty and report tool errors accurately.
Keep the final answer concise and include important outcomes from the tool results."""


def safe_tool_name(server_name: str, tool_name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9_-]", "_", f"{server_name}__{tool_name}")
    return name[:64]


def serialize_tool_result(result: Any) -> str:
    parts: list[str] = []
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if text is not None:
            parts.append(str(text))
        else:
            parts.append(str(item))
    if not parts:
        parts.append(str(result))
    return "\n".join(parts)


class MCPAgentOrchestrator:
    def __init__(
        self,
        config: Settings,
        llm_client: AsyncOpenAI | None = None,
    ) -> None:
        self.config = config
        self.llm = llm_client or AsyncOpenAI(api_key=config.openai_api_key)

    async def _connect(self, stack: AsyncExitStack):
        connected: list[tuple[MCPServerConfig, ClientSession]] = []
        for server in self.config.get_mcp_servers():
            params = StdioServerParameters(
                command=server.command,
                args=server.args,
                env={**__import__("os").environ, **server.env},
                cwd=server.cwd,
            )
            read_stream, write_stream = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
            await session.initialize()
            connected.append((server, session))
        return connected

    async def list_available_tools(self) -> list[dict[str, Any]]:
        async with AsyncExitStack() as stack:
            connected = await self._connect(stack)
            available = []
            for server, session in connected:
                response = await session.list_tools()
                for tool in response.tools:
                    available.append({
                        "name": safe_tool_name(server.name, tool.name),
                        "server": server.name,
                        "description": tool.description or "",
                        "input_schema": tool.inputSchema,
                    })
            return available

    async def run(self, prompt: str) -> dict[str, Any]:
        if not self.config.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        async with AsyncExitStack() as stack:
            connected = await self._connect(stack)
            tool_map: dict[str, tuple[ClientSession, str]] = {}
            tool_specs: list[dict[str, Any]] = []

            for server, session in connected:
                response = await session.list_tools()
                for tool in response.tools:
                    public_name = safe_tool_name(server.name, tool.name)
                    if public_name in tool_map:
                        raise RuntimeError(f"Duplicate tool name after normalization: {public_name}")
                    tool_map[public_name] = (session, tool.name)
                    tool_specs.append({
                        "type": "function",
                        "function": {
                            "name": public_name,
                            "description": (tool.description or "")[:1000],
                            "parameters": tool.inputSchema or {
                                "type": "object",
                                "properties": {},
                            },
                        },
                    })

            messages: list[dict[str, Any]] = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
            trace: list[dict[str, Any]] = []
            rounds = 0

            while rounds < self.config.max_tool_rounds:
                response = await self.llm.chat.completions.create(
                    model=self.config.openai_model,
                    messages=messages,
                    tools=tool_specs or None,
                    tool_choice="auto" if tool_specs else None,
                )
                assistant_message = response.choices[0].message
                assistant_payload: dict[str, Any] = {
                    "role": "assistant",
                    "content": assistant_message.content,
                }
                if assistant_message.tool_calls:
                    assistant_payload["tool_calls"] = [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.function.name,
                                "arguments": call.function.arguments,
                            },
                        }
                        for call in assistant_message.tool_calls
                    ]
                messages.append(assistant_payload)

                if not assistant_message.tool_calls:
                    return {
                        "answer": assistant_message.content or "",
                        "trace": trace,
                        "tool_rounds": rounds,
                    }

                rounds += 1
                for call in assistant_message.tool_calls:
                    public_name = call.function.name
                    try:
                        arguments = json.loads(call.function.arguments or "{}")
                        if not isinstance(arguments, dict):
                            raise ValueError("Tool arguments must be a JSON object")
                        if public_name not in tool_map:
                            raise ValueError(f"Unknown tool: {public_name}")
                        session, original_name = tool_map[public_name]
                        result = await session.call_tool(original_name, arguments)
                        output = serialize_tool_result(result)
                        if getattr(result, "isError", False):
                            output = f"Tool reported an error: {output}"
                        trace.append({
                            "tool": public_name,
                            "arguments": arguments,
                            "result": output,
                            "is_error": bool(getattr(result, "isError", False)),
                        })
                    except Exception as exc:
                        output = f"Tool call failed: {type(exc).__name__}: {exc}"
                        trace.append({
                            "tool": public_name,
                            "arguments": call.function.arguments,
                            "result": output,
                            "is_error": True,
                        })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": output,
                    })

            return {
                "answer": "The orchestration reached the configured tool-call limit before producing a final answer.",
                "trace": trace,
                "tool_rounds": rounds,
            }
