import json as json_module
from typing import Any

from nonebot.drivers import HTTPClientMixin, Request

from .api.login import LoginError, LoginResult
from .api.login import login_flow as api_login_flow
from .utils import log

try:
    import qrcode  # type: ignore
except ImportError:
    qrcode = None


class NoneBotLoginHTTPClient:
    def __init__(self, driver: HTTPClientMixin):
        self.driver = driver

    async def request_json(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        request = Request(
            method=method,
            url=url,
            headers=headers,
            json=json,
            timeout=timeout,
        )
        response = await self.driver.request(request)
        if not (200 <= response.status_code < 300):
            raise LoginError(f"登录请求失败 HTTP 状态码: {response.status_code}")
        if not response.content:
            return {}
        try:
            return json_loads(response.content)
        except json_module.JSONDecodeError as exception:
            raise LoginError("登录接口返回了无效 JSON 数据") from exception


def json_loads(content: bytes | str) -> dict[str, Any]:
    data = json_module.loads(content)
    return data if isinstance(data, dict) else {"data": data}


def _emit_qrcode_message(message: str, *, qrcode_in_info: bool) -> None:
    if qrcode_in_info:
        log("INFO", message)
    else:
        print(message)


def display_qr(qrcode_url: str, *, qrcode_in_info: bool = False) -> None:
    _emit_qrcode_message(
        f"\n请使用微信扫描以下二维码或打开链接: \n{qrcode_url}\n",
        qrcode_in_info=qrcode_in_info,
    )

    if not qrcode:
        _emit_qrcode_message(
            "安装 qrcode 库可在终端直接显示二维码 如: （pip install qrcode）",
            qrcode_in_info=qrcode_in_info,
        )
        return

    qr = qrcode.QRCode(border=1)
    qr.add_data(qrcode_url)
    qr.make(fit=True)

    if qrcode_in_info:
        for row in qr.get_matrix():
            log("INFO", "".join("██" if cell else "  " for cell in row))
    else:
        qr.print_ascii(invert=True)


async def login_flow(
    driver: HTTPClientMixin,
    api_root: str,
    *,
    qrcode_in_info: bool = False,
    local_token_list: list[str] | None = None,
) -> dict[str, str] | None:
    client = NoneBotLoginHTTPClient(driver)

    def message_handler(message: str) -> None:
        log("INFO", message)

    result: LoginResult = await api_login_flow(
        client,
        api_root,
        local_token_list=local_token_list,
        qrcode_handler=lambda url: display_qr(url, qrcode_in_info=qrcode_in_info),
        message_handler=message_handler,
    )

    if result.already_connected:
        return {"already_connected": "true"}
    if not result.connected:
        log("WARNING", result.message or "ClaWeixin login flow finished without token")
        return None

    log("INFO", "登录成功，如需持久化使用请将以下配置写入环境变量")
    log("INFO", f'CLAWEIXIN_TOKEN=["{result.bot_token}"]')
    return {
        "bot_id": result.bot_id,
        "bot_token": result.bot_token,
        "api_root": result.api_root,
    }


def main() -> None:
    from claweixin_login.login import main as cli_main

    cli_main()


if __name__ == "__main__":
    main()
