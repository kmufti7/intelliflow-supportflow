"""Configuration management using pydantic-settings."""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .utils.enums import LLMProvider


def _get_streamlit_secret(key: str) -> Optional[str]:
    """Try to get a secret from Streamlit Cloud secrets.

    Args:
        key: The secret key to look up

    Returns:
        The secret value if found, None otherwise
    """
    try:
        import streamlit as st
        if hasattr(st, "secrets") and key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return None


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = Field(default="IntelliFlow SupportFlow")
    debug: bool = Field(default=False)

    # LLM Provider
    llm_provider: LLMProvider = Field(default=LLMProvider.OPENAI)

    # OpenAI
    openai_api_key: Optional[str] = Field(default=None)
    openai_model: str = Field(default="gpt-4o-mini")

    # Anthropic
    anthropic_api_key: Optional[str] = Field(default=None)
    anthropic_model: str = Field(default="claude-3-haiku-20240307")

    # Database
    database_path: str = Field(default="data/supportflow.db")

    # Logging
    log_level: str = Field(default="INFO")
    log_format: str = Field(default="json")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is a valid Python logging level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return v.upper()

    @field_validator("log_format")
    @classmethod
    def validate_log_format(cls, v: str) -> str:
        """Validate log format."""
        valid_formats = {"json", "console"}
        if v.lower() not in valid_formats:
            raise ValueError(f"Invalid log format: {v}. Must be one of {valid_formats}")
        return v.lower()

    @property
    def database_path_resolved(self) -> Path:
        """Get the resolved database path."""
        return Path(self.database_path)

    @property
    def active_api_key(self) -> Optional[str]:
        """Get the API key for the active provider."""
        if self.llm_provider == LLMProvider.OPENAI:
            return self.openai_api_key
        return self.anthropic_api_key

    @property
    def active_model(self) -> str:
        """Get the model name for the active provider."""
        if self.llm_provider == LLMProvider.OPENAI:
            return self.openai_model
        return self.anthropic_model

    def validate_api_keys(self) -> None:
        """Validate that required API keys are present."""
        from .utils.exceptions import ConfigurationError

        if self.llm_provider == LLMProvider.OPENAI and not self.openai_api_key:
            raise ConfigurationError(
                "OPENAI_API_KEY is required when using OpenAI provider"
            )
        if self.llm_provider == LLMProvider.ANTHROPIC and not self.anthropic_api_key:
            raise ConfigurationError(
                "ANTHROPIC_API_KEY is required when using Anthropic provider"
            )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.

    Checks Streamlit secrets first (for Streamlit Cloud deployment),
    then falls back to environment variables.
    """
    # Try to get API keys from Streamlit secrets first
    openai_key = _get_streamlit_secret("OPENAI_API_KEY")
    anthropic_key = _get_streamlit_secret("ANTHROPIC_API_KEY")

    # Build kwargs for settings, only including secrets if found
    kwargs = {}
    if openai_key:
        kwargs["openai_api_key"] = openai_key
    if anthropic_key:
        kwargs["anthropic_api_key"] = anthropic_key

    return Settings(**kwargs)
