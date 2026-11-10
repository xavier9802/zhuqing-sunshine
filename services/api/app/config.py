from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "zhuqing-sunshine-api"
    app_env: str = "development"
    web_origin: str = "http://localhost:3000"
    database_url: str = "postgresql+psycopg://zhuqing:change-me-locally@localhost:5432/zhuqing"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
