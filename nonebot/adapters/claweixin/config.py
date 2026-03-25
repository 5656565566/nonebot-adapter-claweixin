from typing import Any

from pydantic import BaseModel, Field, field_validator


class Config(BaseModel):
    claweixin_token: list[str] = Field(default_factory=list)
    claweixin_api_root: str = Field(default="https://ilinkai.weixin.qq.com")
    claweixin_login_qrcode_in_info: bool = Field(default=False)

    @field_validator("claweixin_token", mode="before")
    @classmethod
    def normalize_claweixin_token(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            return [token.strip() for token in stripped.replace("\r", "\n").replace(",", "\n").split("\n") if token.strip()]
        if isinstance(value, (list, tuple, set)):
            return [str(token).strip() for token in value if str(token).strip()]
        return [str(value).strip()] if str(value).strip() else []
