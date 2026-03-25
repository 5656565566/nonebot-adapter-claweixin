import base64
import mimetypes
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from nonebot.drivers import HTTPClientMixin, Request

from ..exception import ActionFailed, NetworkError
from .api import send_message
from .cdn.upload import UploadedFileInfo, upload_media_to_cdn

MESSAGE_ITEM_TYPE_TEXT = 1
MESSAGE_ITEM_TYPE_IMAGE = 2
MESSAGE_ITEM_TYPE_VOICE = 3
MESSAGE_ITEM_TYPE_FILE = 4
MESSAGE_ITEM_TYPE_VIDEO = 5
MESSAGE_TYPE_BOT = 2
MESSAGE_STATE_FINISH = 2
UPLOAD_MEDIA_TYPE_IMAGE = 1
UPLOAD_MEDIA_TYPE_VIDEO = 2
UPLOAD_MEDIA_TYPE_FILE = 3


def generate_client_id() -> str:
    return f"claweixin-{os.urandom(8).hex()}"


async def download_remote_media(driver: HTTPClientMixin, url: str) -> str:
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix or ".bin"
    request = Request(method="GET", url=url, timeout=60.0)
    try:
        response = await driver.request(request)
    except Exception as exception:
        raise NetworkError(f"remote media download failed: {exception}") from exception
    if not (200 <= response.status_code < 300):
        raise ActionFailed(response)
    content = response.content
    if content is None:
        payload = b""
    elif isinstance(content, str):
        payload = content.encode()
    else:
        payload = content
    fd, file_path = tempfile.mkstemp(prefix="claweixin-media-", suffix=suffix)
    os.close(fd)
    Path(file_path).write_bytes(payload)
    return file_path


async def ensure_local_file(driver: HTTPClientMixin, media_value: str) -> tuple[str, bool]:
    if "://" in media_value:
        return await download_remote_media(driver, media_value), True
    return media_value, False


async def send_text_message(
    driver,
    *,
    api_root: str,
    token: str,
    to_user_id: str,
    context_token: str | None,
    text: str,
) -> str:
    client_id = generate_client_id()
    await send_message(
        driver,
        api_root=api_root,
        token=token,
        body={
            "msg": {
                "from_user_id": "",
                "to_user_id": to_user_id,
                "client_id": client_id,
                "message_type": MESSAGE_TYPE_BOT,
                "message_state": MESSAGE_STATE_FINISH,
                "context_token": context_token,
                "item_list": [
                    {
                        "type": MESSAGE_ITEM_TYPE_TEXT,
                        "text_item": {"text": text},
                    }
                ],
            }
        },
    )
    return client_id


async def send_media_item(
    driver,
    *,
    api_root: str,
    token: str,
    to_user_id: str,
    context_token: str | None,
    media_item: dict[str, Any],
    text: str = "",
) -> str:
    last_client_id = ""
    if text:
        last_client_id = await send_text_message(
            driver,
            api_root=api_root,
            token=token,
            to_user_id=to_user_id,
            context_token=context_token,
            text=text,
        )

    last_client_id = generate_client_id()
    await send_message(
        driver,
        api_root=api_root,
        token=token,
        body={
            "msg": {
                "from_user_id": "",
                "to_user_id": to_user_id,
                "client_id": last_client_id,
                "message_type": MESSAGE_TYPE_BOT,
                "message_state": MESSAGE_STATE_FINISH,
                "context_token": context_token,
                "item_list": [media_item],
            }
        },
    )
    return last_client_id


def _base64_from_hex(hex_value: str) -> str:
    return base64.b64encode(bytes.fromhex(hex_value)).decode()


def build_image_item(uploaded: UploadedFileInfo) -> dict[str, Any]:
    return {
        "type": MESSAGE_ITEM_TYPE_IMAGE,
        "image_item": {
            "media": {
                "encrypt_query_param": uploaded.download_encrypted_query_param,
                "aes_key": _base64_from_hex(uploaded.aeskey),
                "encrypt_type": 1,
            },
            "mid_size": uploaded.file_size_ciphertext,
        },
    }



def build_video_item(uploaded: UploadedFileInfo) -> dict[str, Any]:
    return {
        "type": MESSAGE_ITEM_TYPE_VIDEO,
        "video_item": {
            "media": {
                "encrypt_query_param": uploaded.download_encrypted_query_param,
                "aes_key": _base64_from_hex(uploaded.aeskey),
                "encrypt_type": 1,
            },
            "video_size": uploaded.file_size_ciphertext,
        },
    }



def build_file_item(uploaded: UploadedFileInfo, file_name: str) -> dict[str, Any]:
    return {
        "type": MESSAGE_ITEM_TYPE_FILE,
        "file_item": {
            "media": {
                "encrypt_query_param": uploaded.download_encrypted_query_param,
                "aes_key": _base64_from_hex(uploaded.aeskey),
                "encrypt_type": 1,
            },
            "file_name": file_name,
            "len": str(uploaded.file_size),
        },
    }


async def send_media_file(
    driver,
    *,
    api_root: str,
    token: str,
    cdn_base_url: str,
    to_user_id: str,
    context_token: str | None,
    file_path: str,
    text: str = "",
) -> str:
    mime, _ = mimetypes.guess_type(file_path)
    mime = mime or "application/octet-stream"

    if mime.startswith("image/"):
        uploaded = await upload_media_to_cdn(
            driver=driver,
            api_root=api_root,
            token=token,
            cdn_base_url=cdn_base_url,
            file_path=file_path,
            to_user_id=to_user_id,
            media_type=UPLOAD_MEDIA_TYPE_IMAGE,
        )
        return await send_media_item(
            driver,
            api_root=api_root,
            token=token,
            to_user_id=to_user_id,
            context_token=context_token,
            media_item=build_image_item(uploaded),
            text=text,
        )

    if mime.startswith("video/"):
        uploaded = await upload_media_to_cdn(
            driver=driver,
            api_root=api_root,
            token=token,
            cdn_base_url=cdn_base_url,
            file_path=file_path,
            to_user_id=to_user_id,
            media_type=UPLOAD_MEDIA_TYPE_VIDEO,
        )
        return await send_media_item(
            driver,
            api_root=api_root,
            token=token,
            to_user_id=to_user_id,
            context_token=context_token,
            media_item=build_video_item(uploaded),
            text=text,
        )

    uploaded = await upload_media_to_cdn(
        driver=driver,
        api_root=api_root,
        token=token,
        cdn_base_url=cdn_base_url,
        file_path=file_path,
        to_user_id=to_user_id,
        media_type=UPLOAD_MEDIA_TYPE_FILE,
    )
    return await send_media_item(
        driver,
        api_root=api_root,
        token=token,
        to_user_id=to_user_id,
        context_token=context_token,
        media_item=build_file_item(uploaded, Path(file_path).name),
        text=text,
    )


async def send_segments(
    driver: HTTPClientMixin,
    *,
    api_root: str,
    token: str,
    cdn_base_url: str,
    to_user_id: str,
    context_token: str | None,
    segments: Iterable[Any],
) -> str:
    last_message_id = ""
    temp_files: list[str] = []
    try:
        for segment in segments:
            segment_type = getattr(segment, "type", None)
            data = getattr(segment, "data", {}) or {}
            if segment_type == "text":
                last_message_id = await send_text_message(
                    driver,
                    api_root=api_root,
                    token=token,
                    to_user_id=to_user_id,
                    context_token=context_token,
                    text=str(data.get("text", "")),
                )
                continue

            if segment_type in {"image", "voice", "file", "video"}:
                media_value = str(
                    data.get("file")
                    or data.get("path")
                    or data.get("url")
                    or ""
                )
                if not media_value:
                    raise ValueError(f"{segment_type} segment missing file/path/url")
                local_path, is_temp = await ensure_local_file(driver, media_value)
                if is_temp:
                    temp_files.append(local_path)
                caption = str(data.get("text", ""))
                last_message_id = await send_media_file(
                    driver,
                    api_root=api_root,
                    token=token,
                    cdn_base_url=cdn_base_url,
                    to_user_id=to_user_id,
                    context_token=context_token,
                    file_path=local_path,
                    text=caption,
                )
                continue

            raise ValueError(f"unsupported segment type: {segment_type}")
    finally:
        for temp_file in temp_files:
            try:
                os.remove(temp_file)
            except OSError:
                pass

    return last_message_id
