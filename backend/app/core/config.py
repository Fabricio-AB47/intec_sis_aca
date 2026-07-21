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

    teams_db_name: str = Field(default="INTECEDUCONTINUA", validation_alias=AliasChoices("DB_NAME4", "B_NAME4", "TEAMS_DB_NAME"))
    teams_db_user: str | None = Field(default=None, validation_alias=AliasChoices("DB_USER4", "TEAMS_DB_USER"))
    teams_db_password: str | None = Field(default=None, validation_alias=AliasChoices("DB_PASSWORD4", "TEAMS_DB_PASSWORD"))
    teams_db_host: str | None = Field(default=None, validation_alias=AliasChoices("DB_HOST4", "TEAMS_DB_HOST"))
    teams_db_port: int | None = Field(default=None, validation_alias=AliasChoices("DB_PORT4", "TEAMS_DB_PORT"))
    teams_db_driver: str | None = Field(default=None, validation_alias=AliasChoices("DB_DRIVER4", "TEAMS_DB_DRIVER"))
    teams_db_encrypt: str | None = Field(default=None, validation_alias=AliasChoices("DB_ENCRYPT4", "TEAMS_DB_ENCRYPT"))
    teams_db_trust_cert: str | None = Field(default=None, validation_alias=AliasChoices("DB_TRUST_CERT4", "TEAMS_DB_TRUST_CERT"))

    expedient_db_name: str = Field(default="INTEC_EXPEDIENTE_ESTUDIANTIL", validation_alias=AliasChoices("EXPEDIENT_DB_NAME", "DB_NAME5", "B_NAME5"))
    expedient_db_user: str | None = Field(default=None, validation_alias=AliasChoices("EXPEDIENT_DB_USER", "DB_USER5"))
    expedient_db_password: str | None = Field(default=None, validation_alias=AliasChoices("EXPEDIENT_DB_PASSWORD", "DB_PASSWORD5"))
    expedient_db_host: str | None = Field(default=None, validation_alias=AliasChoices("EXPEDIENT_DB_HOST", "DB_HOST5"))
    expedient_db_port: int | None = Field(default=None, validation_alias=AliasChoices("EXPEDIENT_DB_PORT", "DB_PORT5"))
    expedient_db_driver: str | None = Field(default=None, validation_alias=AliasChoices("EXPEDIENT_DB_DRIVER", "DB_DRIVER5"))
    expedient_db_encrypt: str | None = Field(default=None, validation_alias=AliasChoices("EXPEDIENT_DB_ENCRYPT", "DB_ENCRYPT5"))
    expedient_db_trust_cert: str | None = Field(default=None, validation_alias=AliasChoices("EXPEDIENT_DB_TRUST_CERT", "DB_TRUST_CERT5"))

    finance_db_name: str = Field(default="INTEC_FINANZAS_INSTITUCIONAL", validation_alias=AliasChoices("FINANCE_DB_NAME", "DB_NAME6", "B_NAME6"))
    finance_db_user: str | None = Field(default=None, validation_alias=AliasChoices("FINANCE_DB_USER", "DB_USER6"))
    finance_db_password: str | None = Field(default=None, validation_alias=AliasChoices("FINANCE_DB_PASSWORD", "DB_PASSWORD6"))
    finance_db_host: str | None = Field(default=None, validation_alias=AliasChoices("FINANCE_DB_HOST", "DB_HOST6"))
    finance_db_port: int | None = Field(default=None, validation_alias=AliasChoices("FINANCE_DB_PORT", "DB_PORT6"))
    finance_db_driver: str | None = Field(default=None, validation_alias=AliasChoices("FINANCE_DB_DRIVER", "DB_DRIVER6"))
    finance_db_encrypt: str | None = Field(default=None, validation_alias=AliasChoices("FINANCE_DB_ENCRYPT", "DB_ENCRYPT6"))
    finance_db_trust_cert: str | None = Field(default=None, validation_alias=AliasChoices("FINANCE_DB_TRUST_CERT", "DB_TRUST_CERT6"))

    graph_db_name: str = Field(default="INTEC_GRAPH_INTEGRACION", validation_alias=AliasChoices("GRAPH_DB_NAME", "DB_NAME7", "B_NAME7"))
    graph_db_user: str | None = Field(default=None, validation_alias=AliasChoices("GRAPH_DB_USER", "DB_USER7"))
    graph_db_password: str | None = Field(default=None, validation_alias=AliasChoices("GRAPH_DB_PASSWORD", "DB_PASSWORD7"))
    graph_db_host: str | None = Field(default=None, validation_alias=AliasChoices("GRAPH_DB_HOST", "DB_HOST7"))
    graph_db_port: int | None = Field(default=None, validation_alias=AliasChoices("GRAPH_DB_PORT", "DB_PORT7"))
    graph_db_driver: str | None = Field(default=None, validation_alias=AliasChoices("GRAPH_DB_DRIVER", "DB_DRIVER7"))
    graph_db_encrypt: str | None = Field(default=None, validation_alias=AliasChoices("GRAPH_DB_ENCRYPT", "DB_ENCRYPT7"))
    graph_db_trust_cert: str | None = Field(default=None, validation_alias=AliasChoices("GRAPH_DB_TRUST_CERT", "DB_TRUST_CERT7"))

    integration_control_db_name: str = Field(default="INTEC_INTEGRACION_CONTROL", validation_alias=AliasChoices("INTEGRATION_CONTROL_DB_NAME", "DB_NAME8", "B_NAME8"))
    integration_control_db_user: str | None = Field(default=None, validation_alias=AliasChoices("INTEGRATION_CONTROL_DB_USER", "DB_USER8"))
    integration_control_db_password: str | None = Field(default=None, validation_alias=AliasChoices("INTEGRATION_CONTROL_DB_PASSWORD", "DB_PASSWORD8"))
    integration_control_db_host: str | None = Field(default=None, validation_alias=AliasChoices("INTEGRATION_CONTROL_DB_HOST", "DB_HOST8"))
    integration_control_db_port: int | None = Field(default=None, validation_alias=AliasChoices("INTEGRATION_CONTROL_DB_PORT", "DB_PORT8"))
    integration_control_db_driver: str | None = Field(default=None, validation_alias=AliasChoices("INTEGRATION_CONTROL_DB_DRIVER", "DB_DRIVER8"))
    integration_control_db_encrypt: str | None = Field(default=None, validation_alias=AliasChoices("INTEGRATION_CONTROL_DB_ENCRYPT", "DB_ENCRYPT8"))
    integration_control_db_trust_cert: str | None = Field(default=None, validation_alias=AliasChoices("INTEGRATION_CONTROL_DB_TRUST_CERT", "DB_TRUST_CERT8"))

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
