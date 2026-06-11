import hashlib
import os
import secrets
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote

from nonebot.drivers import HTTPClientMixin, Request

from ...exception import ActionFailed, NetworkError
from ..api import get_upload_url
from .aes_ecb import aes_ecb_encrypt, aes_ecb_padded_size


@dataclass(slots=True)
class UploadedFileInfo:
    filekey: str
    download_encrypted_query_param: str
    aeskey: str
    file_size: int
    file_size_ciphertext: int


async def upload_buffer_to_cdn(
    driver: HTTPClientMixin,
    *,
    payload: bytes,
    upload_param: str | None = None,
    upload_full_url: str | None = None,
    filekey: str,
    cdn_base_url: str,
    aes_key: bytes,
) -> str:
    encrypted = aes_ecb_encrypt(payload, aes_key)
    if upload_full_url and upload_full_url.strip():
        url = upload_full_url.strip()
    elif upload_param:
        base = cdn_base_url.rstrip("/")
        url = (
            f"{base}/upload?encrypted_query_param={quote(upload_param, safe='')}"
            f"&filekey={quote(filekey, safe='')}"
        )
    else:
        raise NetworkError("cdn upload url missing upload_full_url or upload_param")

    request = Request(
        method="POST",
        url=url,
        headers={"Content-Type": "application/octet-stream"},
        content=encrypted,
        timeout=60.0,
    )
    try:
        response = await driver.request(request)
    except Exception as exception:
        raise NetworkError(f"cdn upload failed: {exception}") from exception
    if not (200 <= response.status_code < 300):
        raise ActionFailed(response)
    download_param = response.headers.get("x-encrypted-param")
    if not download_param:
        raise NetworkError("cdn upload response missing x-encrypted-param header")
    return download_param


async def upload_media_to_cdn(
    *,
    driver: HTTPClientMixin,
    api_root: str,
    token: str,
    cdn_base_url: str,
    payload: bytes,
    to_user_id: str,
    media_type: int,
    bot_agent: str | None = None,
    route_tag: str | None = None,
) -> UploadedFileInfo:
    plaintext = payload
    rawsize = len(plaintext)
    rawfilemd5 = hashlib.md5(plaintext, usedforsecurity=False).hexdigest()
    filesize = aes_ecb_padded_size(rawsize)
    filekey = secrets.token_hex(16)
    aes_key = os.urandom(16)

    upload_url_resp = await get_upload_url(
        driver,
        api_root=api_root,
        token=token,
        body={
            "filekey": filekey,
            "media_type": media_type,
            "to_user_id": to_user_id,
            "rawsize": rawsize,
            "rawfilemd5": rawfilemd5,
            "filesize": filesize,
            "no_need_thumb": True,
            "aeskey": aes_key.hex(),
        },
        bot_agent=bot_agent,
        route_tag=route_tag,
    )
    upload_param: Optional[str] = upload_url_resp.get("upload_param")
    upload_full_url: Optional[str] = upload_url_resp.get("upload_full_url")
    if not upload_param and not upload_full_url:
        raise ValueError("getuploadurl response missing upload_full_url or upload_param")

    download_param = await upload_buffer_to_cdn(
        driver,
        payload=plaintext,
        upload_param=upload_param,
        upload_full_url=upload_full_url,
        filekey=filekey,
        cdn_base_url=cdn_base_url,
        aes_key=aes_key,
    )
    return UploadedFileInfo(
        filekey=filekey,
        download_encrypted_query_param=download_param,
        aeskey=aes_key.hex(),
        file_size=rawsize,
        file_size_ciphertext=filesize,
    )
