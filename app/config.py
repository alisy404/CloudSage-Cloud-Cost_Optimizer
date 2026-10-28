from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    aws_region: str = "ap-south-1"

    # Real AWS is the default application mode. Tests may explicitly override
    # this setting to use the offline adapters.
    aws_mode: bool = True

    # Number of days of CloudWatch history to retrieve (7 first, 30 later).
    cloudwatch_window_days: int = 7

    # Deterministic analysis thresholds (Stage 4).
    # An instance is a rightsizing candidate only when ALL three are satisfied.
    analysis_cpu_avg_threshold: float = 10.0   # % — average must be below this
    analysis_cpu_p95_threshold: float = 25.0   # % — P95 must be below this (spike safety)
    analysis_cpu_max_threshold: float = 50.0   # % — max must be below this (burst safety)
    # Testing only: permits short CloudWatch history and uses maximum as a
    # temporary P95 proxy when a real P95 cannot be calculated.
    analysis_allow_short_window: bool = False

    llm_provider: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_base_url: str = ""
    # Keep the UI responsive when the external provider is overloaded.
    llm_timeout_seconds: float = 10.0
    terraform_apply_enabled: bool = False


settings = Settings()
