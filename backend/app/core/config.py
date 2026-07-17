from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db_name: str = Field(validation_alias=AliasChoices("DB_NAME", "B_NAME"))
    db_user: str
    db_password: str
    db_host: str
    db_port: int = 1433
    db_driver: str = "ODBC Driver 18 for SQL Server"
    db_encrypt: str = "no"
    db_trust_cert: str = "yes"

    eval_db_name: str | None = Field(default=None, validation_alias=AliasChoices("DB_NAME1", "B_NAME1"))
    eval_db_user: str | None = Field(default=None, validation_alias=AliasChoices("DB_USER1"))
    eval_db_password: str | None = Field(default=None, validation_alias=AliasChoices("DB_PASSWORD1"))
    eval_db_host: str | None = Field(default=None, validation_alias=AliasChoices("DB_HOST1"))
    eval_db_port: int = Field(default=1433, validation_alias=AliasChoices("DB_PORT1"))
    eval_db_driver: str | None = Field(default=None, validation_alias=AliasChoices("DB_DRIVER1"))
    eval_db_encrypt: str | None = Field(default=None, validation_alias=AliasChoices("DB_ENCRYPT1"))
    eval_db_trust_cert: str | None = Field(default=None, validation_alias=AliasChoices("DB_TRUST_CERT1"))

    practices_db_name: str | None = Field(default=None, validation_alias=AliasChoices("DB_NAME2", "B_NAME2"))
    practices_db_user: str | None = Field(default=None, validation_alias=AliasChoices("DB_USER2"))
    practices_db_password: str | None = Field(default=None, validation_alias=AliasChoices("DB_PASSWORD2"))
    practices_db_host: str | None = Field(default=None, validation_alias=AliasChoices("DB_HOST2"))
    practices_db_port: int = Field(default=1433, validation_alias=AliasChoices("DB_PORT2"))
    practices_db_driver: str | None = Field(default=None, validation_alias=AliasChoices("DB_DRIVER2"))
    practices_db_encrypt: str | None = Field(default=None, validation_alias=AliasChoices("DB_ENCRYPT2"))
    practices_db_trust_cert: str | None = Field(default=None, validation_alias=AliasChoices("DB_TRUST_CERT2"))

    titulation_db_name: str | None = Field(default=None, validation_alias=AliasChoices("DB_NAME3", "B_NAME3"))
    titulation_db_user: str | None = Field(default=None, validation_alias=AliasChoices("DB_USER3"))
    titulation_db_password: str | None = Field(default=None, validation_alias=AliasChoices("DB_PASSWORD3"))
    titulation_db_host: str | None = Field(default=None, validation_alias=AliasChoices("DB_HOST3"))
    titulation_db_port: int = Field(default=1433, validation_alias=AliasChoices("DB_PORT3"))
    titulation_db_driver: str | None = Field(default=None, validation_alias=AliasChoices("DB_DRIVER3"))
    titulation_db_encrypt: str | None = Field(default=None, validation_alias=AliasChoices("DB_ENCRYPT3"))
    titulation_db_trust_cert: str | None = Field(default=None, validation_alias=AliasChoices("DB_TRUST_CERT3"))

    tenant_id: str | None = Field(default=None, validation_alias=AliasChoices("TENANT_ID", "MS_TENANT_ID"))
    client_id: str | None = Field(default=None, validation_alias=AliasChoices("CLIENT_ID", "MS_CLIENT_ID"))
    client_secret: str | None = Field(default=None, validation_alias=AliasChoices("CLIENT_SECRET", "MS_CLIENT_SECRET"))
    graph_scope: str = Field(default="https://graph.microsoft.com/.default", validation_alias=AliasChoices("GRAPH_SCOPE", "MS_GRAPH_SCOPE"))
    graph_delegate_scopes: str = "User.Read,ChannelMessage.Send,Team.ReadBasic.All,ChannelMessage.Read.All"
    graph_delegate_redirect_uri: str = "http://localhost:8000/api/auth/microsoft/callback"
    graph_user_domain: str | None = Field(default=None, validation_alias=AliasChoices("GRAPH_USER_DOMAIN", "MS_USER_DOMAIN"))
    graph_mail_sender: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GRAPH_MAIL_SENDER",
            "MS_SENDER_EMAIL",
            "MS_SENDER_USER_ID",
            "SENDER_EMAIL",
            "SENDER_USER_ID",
        ),
    )
    frontend_base_url: str = "http://localhost:5174"

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_use_tls: bool = True

    session_secret: str | None = None
    session_cookie_name: str = "reporteria_session"
    session_expire_minutes: int = 480
    session_cookie_secure: bool = False
    session_cookie_samesite: str = "lax"
    auth_legacy_plaintext_enabled: bool = True

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def signing_secret(self) -> str:
        secret = self.session_secret or self.client_secret
        if not secret:
            raise RuntimeError(
                "Debes definir SESSION_SECRET o CLIENT_SECRET para firmar la sesion"
            )
        return secret


def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]
