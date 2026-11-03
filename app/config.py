import json
import os
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MCPServerConfig(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    command: str = Field(min_length=1)
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    cwd: str | None = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    max_tool_rounds: int = Field(default=6, ge=1, le=15)
    mcp_servers_json: str = "[]"

    def get_mcp_servers(self) -> list[MCPServerConfig]:
        try:
            raw = json.loads(self.mcp_servers_json)
        except json.JSONDecodeError as exc:
            raise ValueError("MCP_SERVERS_JSON must be valid JSON") from exc
        if not isinstance(raw, list):
            raise ValueError("MCP_SERVERS_JSON must contain a JSON array")
        return [MCPServerConfig.model_validate(item) for item in raw]


settings = Settings()
