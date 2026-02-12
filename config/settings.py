"""
Configuration management using Pydantic Settings.

Environment variables are loaded from .env file or system environment.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RobotConfig(BaseSettings):
    """Configuration for a single robot"""
    name: str
    host: str
    port: int
    cell_heights: list[float] = Field(default_factory=lambda: [0.5, 1.0, 1.5])


class Settings(BaseSettings):
    """Main application settings"""

    # Redis Configuration
    redis_host: str = Field(default="localhost", description="Redis server host")
    redis_port: int = Field(default=6379, description="Redis server port")

    # Supabase Configuration
    supabase_url: str = Field(description="Supabase project URL")
    supabase_key: str = Field(description="Supabase anon/service key")
    graph_id: int = Field(default=1, description="Graph ID for path planning")

    # Server Configuration
    host: str = Field(default="127.0.0.1", description="Server host")
    port: int = Field(default=8000, description="Server port")
    reload: bool = Field(default=True, description="Enable auto-reload in development")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


# Singleton instance
settings = Settings()
