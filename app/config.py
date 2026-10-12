from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    aws_region: str = "ap-south-1"

    # When True the app uses real AWS APIs; when False it uses the fake adapter.
    aws_mode: bool = False

    # Number of days of CloudWatch history to retrieve (7 first, 30 later).
    cloudwatch_window_days: int = 7

    llm_provider: str = ""
    llm_api_key: str = ""


settings = Settings()
