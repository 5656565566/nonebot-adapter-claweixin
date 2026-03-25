import asyncio
import json
from typing import Any

from nonebot.drivers import HTTPClientMixin, Request

from .utils import log

try:
    import qrcode  # type: ignore
except ImportError:
    qrcode = None


DEFAULT_BOT_TYPE = "3"


class LoginError(RuntimeError):
    pass


async def _request_json(
    driver: HTTPClientMixin,
    request: Request,
    *,
    read_timeout_as_wait: bool = False,
) -> dict[str, Any]:
    try:
        response = await driver.request(request)
    except TimeoutError:
        if read_timeout_as_wait:
            return {"status": "wait"}
        raise

    if not (200 <= response.status_code < 300):
        raise LoginError(f"登录请求失败 HTTP 状态码: {response.status_code}")
    if not response.content:
        return {}

    try:
        return json.loads(response.content)
    except json.JSONDecodeError as exception:
        raise LoginError("登录接口返回了无效 JSON 数据") from exception


async def fetch_qrcode(
    driver: HTTPClientMixin,
    api_root: str,
    bot_type: str = DEFAULT_BOT_TYPE,
) -> dict[str, Any]:
    request = Request(
        method="GET",
        url=f"{api_root.rstrip('/')}/ilink/bot/get_bot_qrcode?bot_type={bot_type}",
        timeout=10.0,
    )
    return await _request_json(driver, request)


async def poll_qr_status(
    driver: HTTPClientMixin,
    api_root: str,
    qrcode_id: str,
) -> dict[str, Any]:
    request = Request(
        method="GET",
        url=f"{api_root.rstrip('/')}/ilink/bot/get_qrcode_status?qrcode={qrcode_id}",
        headers={"iLink-App-ClientVersion": "1"},
        timeout=35.0,
    )
    return await _request_json(driver, request, read_timeout_as_wait=True)


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
) -> dict[str, str] | None:
    log("INFO", "未配置任何 CLAWEIXIN_TOKEN 开始登录流程")
    qr_data = await fetch_qrcode(driver, api_root)
    qrcode_id = str(qr_data.get("qrcode") or "")
    qrcode_url = str(qr_data.get("qrcode_img_content") or "")

    if not qrcode_id or not qrcode_url:
        raise LoginError("获取登录二维码失败 返回数据缺少 qrcode 或 qrcode_img_content")

    display_qr(qrcode_url, qrcode_in_info=qrcode_in_info)
    log("INFO", "等待扫码确认登录...")

    while True:
        status_data = await poll_qr_status(driver, api_root, qrcode_id)
        status = status_data.get("status")

        if status == "wait":
            await asyncio.sleep(2)
            continue
        if status == "scaned":
            log("INFO", "二维码已扫码，请在手机上确认登录")
            await asyncio.sleep(2)
            continue
        if status == "expired":
            raise LoginError("二维码已过期，请重新启动应用后再次登录")
        if status == "confirmed":
            bot_id = str(status_data.get("ilink_bot_id") or "")
            bot_token = str(status_data.get("bot_token") or "")
            resolved_api_root = str(status_data.get("baseurl") or api_root)
            if not bot_token:
                raise LoginError("登录成功但接口未返回 bot_token")

            log("INFO", "登录成功，请将以下配置写入环境变量")
            log("INFO", f'CLAWEIXIN_TOKEN=["{bot_token}"]')
            # log("INFO", f'CLAWEIXIN_API_ROOT="{resolved_api_root}"')
            return {
                "bot_id": bot_id,
                "bot_token": bot_token,
                "api_root": resolved_api_root,
            }

        raise LoginError(f"未知登录状态: {status}")


if __name__ == "__main__":
    raise SystemExit("请在 nonebot 适配器初始化流程中调用 login_flow 而不是直接运行该模块")
