from pydantic import Field, BaseModel

class Config(BaseModel):
    claweixin_token: str = Field(default="")
    claweixin_api_root: str = Field(default="https://ilinkai.weixin.qq.com")
