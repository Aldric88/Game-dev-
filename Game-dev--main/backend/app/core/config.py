import logging
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

_config_logger = logging.getLogger(__name__)


def _load_env_file() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            name, _, value = line.partition("=")
            os.environ.setdefault(name.strip(), value.strip())


def _get_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in ("1", "true", "yes")


def _get_int(name: str, default: int = 0) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _ensure_jwt_secret() -> None:
    """If JWT_SECRET_KEY is not in the environment, generate one and persist it
    to the .env file so it survives application restarts in development."""
    if os.getenv("JWT_SECRET_KEY"):
        return
    generated = secrets.token_hex(32)
    os.environ["JWT_SECRET_KEY"] = generated
    env_path = Path(__file__).resolve().parents[2] / ".env"
    try:
        existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
        if "JWT_SECRET_KEY" not in existing:
            with env_path.open("a", encoding="utf-8") as f:
                f.write(f"\nJWT_SECRET_KEY={generated}\n")
            _config_logger.info(
                "Generated JWT_SECRET_KEY and saved to %s. "
                "This key will now persist across restarts.",
                env_path,
            )
        else:
            _config_logger.warning(
                "JWT_SECRET_KEY found in .env file but was not loaded into the environment. "
                "A new key has been generated for this session only."
            )
    except OSError as exc:
        _config_logger.warning(
            "Could not persist JWT_SECRET_KEY to .env (%s). "
            "Sessions will be invalidated on next restart. "
            "Set JWT_SECRET_KEY as an environment variable to fix this.",
            exc,
        )


_load_env_file()
_ensure_jwt_secret()


@dataclass
class Settings:
    mongodb_uri: str = os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017")
    mongodb_db_name: str = os.getenv("MONGODB_DB_NAME", "game_ai_platform")
    allow_inmemory_fallback: bool = _get_bool("ALLOW_INMEMORY_FALLBACK", True)

    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    access_token_expire_minutes: int = _get_int("ACCESS_TOKEN_EXPIRE_MINUTES", 1440)

    ai_provider: str = os.getenv("AI_PROVIDER", "auto")

    gemini_api_key: str = os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", ""))
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    ai_local_base_url: str = os.getenv("AI_LOCAL_BASE_URL", "")
    ai_local_model: str = os.getenv("AI_LOCAL_MODEL", "local-model")
    ai_local_api_key: str = os.getenv("AI_LOCAL_API_KEY", "")

    ai_request_timeout_seconds: int = _get_int("AI_REQUEST_TIMEOUT_SECONDS", 120)
    ai_max_retries: int = _get_int("AI_MAX_RETRIES", 2)
    ai_max_requests_per_minute: int = _get_int("AI_MAX_REQUESTS_PER_MINUTE", 60)

    aws_access_key_id: str = os.getenv("AWS_ACCESS_KEY_ID", "")
    aws_secret_access_key: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    aws_region: str = os.getenv("AWS_REGION", "us-east-1")
    s3_bucket_name: str = os.getenv("S3_BUCKET_NAME", "")

    redis_url: str = os.getenv("REDIS_URL", "")

    # Comma-separated allowed CORS origins.
    # Default "*" is fine for local dev. In production set to your frontend domain,
    # e.g. CORS_ORIGINS=https://app.example.com
    cors_origins: str = os.getenv("CORS_ORIGINS", "http://localhost:5173")

    # Set to true only when the app itself terminates TLS (not a reverse proxy).
    enforce_https: bool = _get_bool("ENFORCE_HTTPS", False)

    default_credits_free: int = _get_int("DEFAULT_CREDITS_FREE", 10)
    default_credits_pro: int = _get_int("DEFAULT_CREDITS_PRO", 100)


settings = Settings()

PLAN_LIMITS: dict[str, int] = {
    "free": settings.default_credits_free,
    "pro": settings.default_credits_pro,
    "enterprise": -1,  # unlimited
}
