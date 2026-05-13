"""Configuration management with validation"""
from pydantic import BaseSettings, Field, validator
from typing import Optional


class Settings(BaseSettings):
    """Application settings with validation"""

    # API Keys (required)
    GROQ_API_KEY: str = Field(..., env="GROQ_API_KEY")
    OPENROUTER_API_KEY: str = Field(..., env="OPENROUTER_API_KEY")
    GEMINI_API_KEY: str = Field(..., env="GEMINI_API_KEY")

    # AngelOne (required for NSE data)
    ANGEL_API_KEY: str = Field(..., env="ANGEL_API_KEY")
    ANGEL_CLIENT_ID: str = Field(..., env="ANGEL_CLIENT_ID")
    ANGEL_PASSWORD: str = Field(..., env="ANGEL_PASSWORD")
    ANGEL_TOTP_SECRET: str = Field(..., env="ANGEL_TOTP_SECRET")

    # Telegram (optional)
    TELEGRAM_BOT_TOKEN: Optional[str] = Field(None, env="TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID: Optional[str] = Field(None, env="TELEGRAM_CHAT_ID")

    # Security
    API_KEY: str = Field("dev-key-change-in-production", env="API_KEY")
    CORS_ORIGINS: str = Field("*", env="CORS_ORIGINS")

    # Database
    DATABASE_URL: str = Field("sqlite:///trading_signals.db", env="DATABASE_URL")

    # Logging
    LOG_LEVEL: str = Field("INFO", env="LOG_LEVEL")
    LOG_DIR: str = Field("/opt/share-market/logs", env="LOG_DIR")

    # Trading Parameters
    VIX_THRESHOLD: float = Field(18.0, env="VIX_THRESHOLD")
    CONFIDENCE_THRESHOLD_BUY_SELL: int = Field(65, env="CONFIDENCE_THRESHOLD_BUY_SELL")
    CONFIDENCE_THRESHOLD_HOLD: int = Field(85, env="CONFIDENCE_THRESHOLD_HOLD")

    # Price Loop
    PRICE_UPDATE_INTERVAL: int = Field(5, env="PRICE_UPDATE_INTERVAL")

    # Token Limits
    GROQ_DAILY_LIMIT: int = Field(500_000, env="GROQ_DAILY_LIMIT")
    GEMINI_DAILY_LIMIT: int = Field(1_000_000, env="GEMINI_DAILY_LIMIT")

    @validator("CORS_ORIGINS")
    def parse_cors_origins(cls, v):
        """Split comma-separated CORS origins"""
        if v == "*":
            return ["*"]
        return [origin.strip() for origin in v.split(",")]

    @validator("LOG_LEVEL")
    def validate_log_level(cls, v):
        """Ensure valid log level"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid LOG_LEVEL. Must be one of: {valid_levels}")
        return v.upper()

    @validator("VIX_THRESHOLD")
    def validate_vix_threshold(cls, v):
        """Ensure VIX threshold is reasonable"""
        if not (5 <= v <= 50):
            raise ValueError("VIX_THRESHOLD must be between 5 and 50")
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Global settings instance
settings = Settings()
