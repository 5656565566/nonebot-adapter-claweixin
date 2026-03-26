import argparse
import asyncio
import json
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request as URLRequest, urlopen

from nonebot.drivers import HTTPClientMixin, Request, Response

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
    except Exception as e:
        error_name = e.__class__.__name__
        if "Timeout" in error_name or isinstance(e, TimeoutError):
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
    timeout: float = 35.0,
) -> dict[str, Any]:
    request = Request(
        method="GET",
        url=f"{api_root.rstrip('/')}/ilink/bot/get_qrcode_status?qrcode={qrcode_id}",
        headers={"iLink-App-ClientVersion": "1"},
        timeout=timeout,
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
    log("INFO", "等待扫码确认登录（限时 30 秒）...")

    start_time = time.time()
    max_wait = 30.0

    while True:
        elapsed = time.time() - start_time
        if elapsed >= max_wait:
            log("WARNING", "登录超时（超过 30 秒未完成扫码）请重新启动应用")
            return

        poll_timeout = min(35.0, max_wait - elapsed)
        status_data = await poll_qr_status(driver, api_root, qrcode_id, timeout=poll_timeout)
        status = status_data.get("status")

        if status == "wait":
            if time.time() - start_time < max_wait:
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

            log("INFO", "登录成功，如需持久化使用请将以下配置写入环境变量")
            log("INFO", f'CLAWEIXIN_TOKEN=["{bot_token}"]')
            # log("INFO", f'CLAWEIXIN_API_ROOT="{resolved_api_root}"')
            return {
                "bot_id": bot_id,
                "bot_token": bot_token,
                "api_root": resolved_api_root,
            }

        raise LoginError(f"未知登录状态: {status}")


class _CliHTTPDriver(HTTPClientMixin):
    @property
    def type(self) -> str:
        return "claweixin-cli"

    async def request(self, setup: Request) -> Response:
        return await asyncio.to_thread(self._request_sync, setup)

    async def stream_request(self, setup: Request):
        raise NotImplementedError("CLI 登录流程不需要 stream_request")

    async def get_session(self):
        raise NotImplementedError("CLI 登录流程不需要 get_session")

    def _request_sync(self, setup: Request) -> Response:
        body = setup.content
        if isinstance(body, str):
            body = body.encode("utf-8")

        request = URLRequest(
            url=str(setup.url),
            data=body,
            method=setup.method,
            headers=dict(setup.headers),
        )

        timeout = None
        if isinstance(setup.timeout, (int, float)):
            timeout = float(setup.timeout)

        try:
            with urlopen(request, timeout=timeout) as response:
                return Response(
                    response.status,
                    headers=dict(response.headers.items()),
                    content=response.read(),
                    request=setup,
                )
        except HTTPError as exception:
            return Response(
                exception.code,
                headers=dict(exception.headers.items()),
                content=exception.read(),
                request=setup,
            )
        except TimeoutError:
            raise
        except URLError as exception:
            reason = exception.reason
            if isinstance(reason, TimeoutError):
                raise reason
            raise RuntimeError(f"登录请求失败: {reason}") from exception


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ClaWeixin 登录工具")
    parser.add_argument(
        "--api-root",
        default="https://ilinkai.weixin.qq.com",
        help="Weixin API 根地址",
    )
    parser.add_argument(
        "--qrcode-in-info",
        action="store_true",
        help="通过 nonebot logger 输出二维码，而不是直接打印到标准输出",
    )
    return parser


async def _run_cli_login(api_root: str, *, qrcode_in_info: bool) -> int:
    driver = _CliHTTPDriver()
    try:
        result = await login_flow(driver, api_root, qrcode_in_info=qrcode_in_info)
    except LoginError as exception:
        print(f"claweixin-login 失败: {exception}", file=sys.stderr)
        return 1
    except Exception as exception:
        print(f"claweixin-login 失败: {exception}", file=sys.stderr)
        return 1

    if not result:
        return 1
    return 0


def main() -> None:
    parser = _build_argument_parser()
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run_cli_login(args.api_root, qrcode_in_info=args.qrcode_in_info)))


if __name__ == "__main__":
    main()

