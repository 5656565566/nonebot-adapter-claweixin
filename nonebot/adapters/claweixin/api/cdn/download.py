import base64

from nonebot.drivers import HTTPClientMixin, Request

from ...exception import ActionFailed, NetworkError
from .aes_ecb import decrypt_aes_ecb
from .url import build_cdn_download_url


def parse_aes_key(aes_key_base64: str) -> bytes:
    decoded = base64.b64decode(aes_key_base64)
    if len(decoded) == 16:
        return decoded
    if len(decoded) == 32:
        try:
            text = decoded.decode("ascii")
        except UnicodeDecodeError as exception:
            raise ValueError("invalid aes_key ascii payload") from exception
        if all(char in "0123456789abcdefABCDEF" for char in text):
            return bytes.fromhex(text)
    raise ValueError("aes_key must decode to 16 raw bytes or 32-char hex string")


async def fetch_cdn_bytes(driver: HTTPClientMixin, url: str) -> bytes:
    request = Request(method="GET", url=url, timeout=30.0)
    try:
        response = await driver.request(request)
    except Exception as exception:
        raise NetworkError(f"cdn download failed: {exception}") from exception
    if not (200 <= response.status_code < 300):
        raise ActionFailed(response)
    content = response.content
    if content is None:
        return b""
    if isinstance(content, str):
        return content.encode()
    return content


async def download_plain_cdn_buffer(
    driver: HTTPClientMixin,
    encrypted_query_param: str,
    cdn_base_url: str,
) -> bytes:
    url = build_cdn_download_url(encrypted_query_param, cdn_base_url)
    return await fetch_cdn_bytes(driver, url)


async def download_and_decrypt_buffer(
    driver: HTTPClientMixin,
    encrypted_query_param: str,
    aes_key_base64: str,
    cdn_base_url: str,
) -> bytes:
    key = parse_aes_key(aes_key_base64)
    encrypted = await download_plain_cdn_buffer(driver, encrypted_query_param, cdn_base_url)
    return decrypt_aes_ecb(encrypted, key)
