"""Settings loaded from the .env file at the project root (pydantic-settings)."""
import os
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",   # works from notebooks/, server/, scripts/ or tests/
        env_file_encoding="utf-8",
        extra="ignore",                   # .env also has HOST, PORT, ... that we don't need here
    )

    openai_api_key: str = ""
    # OPENAI_MODEL is the name in .env.example; MODEL is still accepted for the old notebooks
    openai_model: str = Field("gpt-4.1-mini", validation_alias=AliasChoices("OPENAI_MODEL", "MODEL"))
    guardrail_model: str = "gpt-5.4-nano"   # cheap, fast model for guardrail agents (gpt-4.1-nano is retired)
    vector_store_id: str | None = None
    database_url: str = "sqlite:///./chatbot.sqlite3"
    allowed_origins: str = "http://localhost:5500,http://127.0.0.1:5500"   # comma-separated
    rate_limit_per_hour: int = 20
    app_env: str = "development"
    # X-Forwarded-For is only trusted when the request comes from one of these (our Nginx proxy)
    trusted_proxy_ips: str = "127.0.0.1,::1"   # comma-separated

    # Agent memory: how many session items (messages, tool calls, tool results) the model sees per turn
    session_history_limit: int = 40
    # OpenAI traces: False = spans are kept but model inputs/outputs and tool arguments/results are
    # left out (visitor messages, names, phone numbers). Set TRACE_INCLUDE_SENSITIVE_DATA=true only
    # locally while debugging.
    trace_include_sensitive_data: bool = False

    # Email to the Coltek team after every new lead or demo request (chatbot/notify.py).
    # Resend uses HTTPS; SMTP remains available as a fallback/legacy backend.
    email_backend: str = "smtp"
    resend_api_key: str = ""
    default_from_email: str = ""
    smtp_host: str = Field("", validation_alias=AliasChoices("EMAIL_SMTP_SERVER", "SMTP_HOST"))
    smtp_port: int = 587
    smtp_user: str = Field("", validation_alias=AliasChoices("EMAIL_ADDRESS", "SMTP_USER"))
    smtp_password: str = Field("", validation_alias=AliasChoices("EMAIL_APP_PASSWORD", "SMTP_PASSWORD"))
    smtp_use_tls: bool = True          # STARTTLS on port 587; set False for port 25 / local test servers
    smtp_from: str = ""                # defaults to smtp_user if empty
    notify_email_to: str = ""          # comma-separated team addresses

    # Optional private conversation viewer at /admin (HTTP Basic authentication).
    admin_username: str = ""
    admin_password: str = ""

    @property
    def allowed_origins_list(self) -> list[str]:
        """ALLOWED_ORIGINS split into a list, e.g. for FastAPI CORS."""
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def trusted_proxy_ips_list(self) -> list[str]:
        return [ip.strip() for ip in self.trusted_proxy_ips.split(",") if ip.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


settings = Settings()

# The OpenAI client and the Agents SDK read the key from the environment, so make sure it is there.
if settings.openai_api_key and not os.environ.get("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = settings.openai_api_key

# The Agents SDK reads this variable whenever a RunConfig is created (agents/run_config.py,
# default "true"). Setting it here also covers runs that get no RunConfig from us, such as the
# guardrails' classifier and output-checker runs.
os.environ["OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA"] = "true" if settings.trace_include_sensitive_data else "false"

# Short names used across chatbot/ and the notebooks
MODEL = settings.openai_model
GUARDRAIL_MODEL = settings.guardrail_model
VECTOR_STORE_ID = settings.vector_store_id
