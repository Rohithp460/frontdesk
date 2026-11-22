import secrets
from typing import List, Union
from pydantic import PrivateAttr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Frontdesk API"
    ENVIRONMENT: str = "development"
    API_V1_STR: str = "/api/v1"

    # JWT Settings
    JWT_SECRET: Union[str, None] = None
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # MySQL Database Settings
    MYSQL_SERVER: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "frontdesk"
    MYSQL_PASSWORD: str = "frontdesk_password"
    MYSQL_DB: str = "frontdesk_db"
    DATABASE_URL: Union[str, None] = None

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    _development_jwt_secret: str = PrivateAttr(
        default_factory=lambda: secrets.token_urlsafe(48)
    )

    @model_validator(mode="after")
    def require_secure_production_jwt_secret(self) -> "Settings":
        if self.ENVIRONMENT.lower() == "production":
            secret = self.JWT_SECRET
            lowered = secret.lower() if secret else ""
            if (
                not secret
                or len(secret) < 32
                or len(set(secret)) < 12
                or any(marker in lowered for marker in ("changeme", "replace", "example", "development", "your-secret"))
            ):
                raise ValueError("A strong JWT_SECRET of at least 32 characters is required in production")
        return self

    @property
    def jwt_secret(self) -> str:
        if self.JWT_SECRET:
            return self.JWT_SECRET
        if self.ENVIRONMENT.lower() == "production":
            raise RuntimeError("JWT_SECRET is required in production")
        return self._development_jwt_secret

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    @property
    def sync_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_SERVER}:{self.MYSQL_PORT}/{self.MYSQL_DB}"
        )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
