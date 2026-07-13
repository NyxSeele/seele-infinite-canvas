import os
from pathlib import Path

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent

WEAK_JWT_SECRETS = {
    "",
    "change-me-in-production-aistudio-2026",
    "change-me-to-a-long-random-string",
    "change-me-to-a-long-random-string-at-least-16-chars",
    "你的随机密钥",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            str(_BACKEND_DIR / ".env"),
            str(_BACKEND_DIR.parent / ".env"),
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    jwt_secret: str = Field(
        default="",
        validation_alias=AliasChoices("JWT_SECRET", "JWT_SECRET_KEY"),
    )
    api_key_encrypt_secret: str = Field(
        default="",
        validation_alias=AliasChoices("API_KEY_ENCRYPT_SECRET"),
        description="Fernet 派生密钥；未设时回退 JWT_SECRET",
    )
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=120)
    refresh_token_expire_days: int = 30

    database_url: str = Field(default="", validation_alias="DATABASE_URL")

    dashscope_api_key: str = Field(
        default="", validation_alias=AliasChoices("DASHSCOPE_API_KEY")
    )
    deepseek_api_key: str = Field(
        default="", validation_alias=AliasChoices("DEEPSEEK_API_KEY")
    )
    agent_model: str = Field(
        default="deepseek-v3",
        validation_alias=AliasChoices("AGENT_MODEL", "AGENT_MODEL_STRING"),
    )
    optimize_timeout: float = 32.0
    tasks_cache_ttl: float = 3.0
    # Cloudflare Free ~100s idle limit; keep LLM HTTP under that.
    llm_http_timeout: float = Field(
        default=90.0,
        validation_alias=AliasChoices("LLM_HTTP_TIMEOUT"),
    )
    agent_sse_keepalive_sec: float = Field(
        default=25.0,
        validation_alias=AliasChoices("AGENT_SSE_KEEPALIVE_SEC"),
    )
    media_download_timeout: float = Field(
        default=120.0,
        validation_alias=AliasChoices("MEDIA_DOWNLOAD_TIMEOUT"),
        description="后台下载外部视频用于探测的超时（秒）",
    )

    comfyui_url: str = Field(
        default="http://127.0.0.1:8000",
        validation_alias=AliasChoices("COMFYUI_URL", "COMFYUI_BASE"),
    )
    comfyui_ws_url: str = Field(
        default="",
        validation_alias=AliasChoices("COMFYUI_WS_URL"),
    )

    redis_url: str = Field(default="redis://127.0.0.1:6379/0", validation_alias="REDIS_URL")

    seedance_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("SEEDANCE_API_KEY", "ARK_API_KEY"),
    )
    seedance_api_base: str = Field(
        default="https://ark.cn-beijing.volces.com/api/v3",
        validation_alias=AliasChoices("SEEDANCE_API_BASE"),
    )
    seedance_model_id: str = Field(
        default="doubao-seedance-2-0-260128",
        validation_alias=AliasChoices("SEEDANCE_MODEL_ID"),
    )

    agent_mock_generation: bool = Field(
        default=False,
        validation_alias=AliasChoices("AGENT_MOCK_GENERATION"),
    )
    agent_mock_failure_rate: float = Field(
        default=0.0,
        validation_alias=AliasChoices("AGENT_MOCK_FAILURE_RATE"),
    )

    agent_llm_max_retries: int = Field(default=3, validation_alias="AGENT_LLM_MAX_RETRIES")
    agent_llm_retry_base_delay: float = Field(
        default=1.0,
        validation_alias="AGENT_LLM_RETRY_BASE_DELAY",
    )

    app_env: str = Field(default="development", validation_alias="APP_ENV")
    cors_origins: str = Field(default="", validation_alias="CORS_ORIGINS")

    rate_limit_per_minute: int = Field(default=120)
    rate_limit_user_per_minute: int = Field(default=60)
    login_rate_limit_per_minute: int = Field(
        default=30,
        validation_alias=AliasChoices("LOGIN_RATE_LIMIT_PER_MINUTE"),
    )
    login_max_failures: int = Field(
        default=5,
        validation_alias=AliasChoices("LOGIN_MAX_FAILURES"),
    )
    login_lock_minutes: int = Field(
        default=15,
        validation_alias=AliasChoices("LOGIN_LOCK_MINUTES"),
    )
    agent_rate_limit_user_per_minute: int = Field(
        default=20,
        validation_alias=AliasChoices("AGENT_RATE_LIMIT_USER_PER_MINUTE"),
    )
    seed_admin_password: str = Field(
        default="",
        validation_alias=AliasChoices("SEED_ADMIN_PASSWORD"),
    )
    seed_testuser_password: str = Field(
        default="",
        validation_alias=AliasChoices("SEED_TESTUSER_PASSWORD"),
    )
    seed_testuser2_password: str = Field(
        default="",
        validation_alias=AliasChoices("SEED_TESTUSER2_PASSWORD"),
    )
    generation_max_concurrent: int = Field(default=3)
    generation_max_concurrent_team: int = Field(default=10)
    media_token_ttl_seconds: int = Field(default=14400)

    canvas_lock_ttl_seconds: int = Field(default=90)
    canvas_heartbeat_seconds: int = Field(default=25)

    @model_validator(mode="after")
    def require_jwt_secret(self) -> "Settings":
        if self.jwt_secret in WEAK_JWT_SECRETS:
            raise ValueError(
                "必须在 .env 中设置 JWT_SECRET（或 JWT_SECRET_KEY），"
                "且不能使用默认值，请使用至少 16 位的随机字符串"
            )
        if len(self.jwt_secret) < 16:
            raise ValueError("JWT_SECRET 长度至少 16 个字符")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        raw = (self.cors_origins or "").strip()
        if raw:
            return [origin.strip() for origin in raw.split(",") if origin.strip()]
        return [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:8173",
            "http://127.0.0.1:8173",
            "http://localhost:8174",
            "http://127.0.0.1:8174",
        ]

    @property
    def sqlalchemy_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return "sqlite:///./aistudio.db"


def load_settings() -> Settings:
    return Settings()


# 启动时校验；导入失败则进程无法启动
settings = load_settings()
