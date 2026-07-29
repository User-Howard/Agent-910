import sys
from typing import Literal

from pydantic import BaseModel, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

AllowedModel = Literal[
    "openai:gpt-5.6-terra",
    "openai:gpt-5.6-luna",
    "openai:gpt-4.1-nano",
]


class LLMSettings(BaseModel):
    endpoint: str = "https://api.openai.com/v1"
    model: AllowedModel = "openai:gpt-5.6-terra"
    api_key: str


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
        populate_by_name=True,
    )

    discord_token: str
    llm: LLMSettings

    initial_history: int = 10


def load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as e:
        print(e)
        sys.exit(1)


settings = load_settings()
