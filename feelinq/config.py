from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    telegram_bot_token: str
    postgres_dsn: str = "postgresql://feelinq:feelinq@localhost:5432/feelinq"
    influx_host: str = "localhost"
    influx_port: int = 8181
    influx_token: str = ""
    influx_database: str = "feelinq"
    admin_user_ids: str = ""
    log_level: str = "INFO"

    @property
    def admin_ids_list(self) -> list[str]:
        return [s.strip() for s in self.admin_user_ids.split(",") if s.strip()]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()  # type: ignore[call-arg]
