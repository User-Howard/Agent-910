import sys
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True
    )

    discord_token: str
    api_key: str = Field(alias="OPENAI_API_KEY")

    openai_model: str = "openai:gpt-4o"
    initial_history: int = 10

def load_settings() -> Settings:
    try:
        return Settings()
    except Exception as e:
        print(e)
        sys.exit(1)


settings = load_settings()
