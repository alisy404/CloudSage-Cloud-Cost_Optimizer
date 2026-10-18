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

    # Deterministic analysis thresholds (Stage 4).
    # An instance is a rightsizing candidate only when ALL three are satisfied.
    analysis_cpu_avg_threshold: float = 10.0   # % — average must be below this
    analysis_cpu_p95_threshold: float = 25.0   # % — P95 must be below this (spike safety)
    analysis_cpu_max_threshold: float = 50.0   # % — max must be below this (burst safety)

    llm_provider: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_base_url: str = ""
    llm_timeout_seconds: float = 30.0


settings = Settings()
