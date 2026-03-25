import base64
import mimetypes
import os
from io import BytesIO
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
UPLOAD_MEDIA_TYPE_VOICE = 4


def generate_client_id() -> str:
    return f"claweixin-{os.urandom(8).hex()}"


async def download_remote_media(driver: HTTPClientMixin, url: str) -> tuple[bytes, str | None]:
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
    return payload, Path(parsed.path).name or f"remote-media{suffix}"


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
) -> str:
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
    return base64.b64encode(hex_value.encode()).decode()


def build_image_item(uploaded: UploadedFileInfo) -> dict[str, Any]:
    return {
        "type": MESSAGE_ITEM_TYPE_IMAGE,
        "image_item": {
            "media": {
                "encrypt_query_param": uploaded.download_encrypted_query_param,
                "aes_key": _base64_from_hex(uploaded.aeskey),
                "encrypt_type": 1,
            },
            "mid_size": uploaded.file_size,
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
            "video_size": uploaded.file_size,
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


def build_voice_item(
    uploaded: UploadedFileInfo,
    text: str = "",
    encode_type: int | None = None,
    bits_per_sample: int | None = None,
    sample_rate: int | None = None,
    playtime: int | None = None,
) -> dict[str, Any]:
    voice_item: dict[str, Any] = {
        "type": MESSAGE_ITEM_TYPE_VOICE,
        "voice_item": {
            "media": {
                "encrypt_query_param": uploaded.download_encrypted_query_param,
                "aes_key": _base64_from_hex(uploaded.aeskey),
                "encrypt_type": 1,
            },
        },
    }
    if text:
        voice_item["voice_item"]["text"] = text
    if encode_type is not None:
        voice_item["voice_item"]["encode_type"] = encode_type
    if bits_per_sample is not None:
        voice_item["voice_item"]["bits_per_sample"] = bits_per_sample
    if sample_rate is not None:
        voice_item["voice_item"]["sample_rate"] = sample_rate
    if playtime is not None:
        voice_item["voice_item"]["playtime"] = playtime
    return voice_item


def normalize_binary_file(data: bytes | BytesIO | Path) -> tuple[bytes, str | None]:
    if isinstance(data, bytes):
        return data, None
    if isinstance(data, BytesIO):
        return data.getvalue(), None
    return data.read_bytes(), data.name


def infer_media_kind(file_name: str | None, mime_type: str | None, *, force_voice: bool = False) -> str:
    if force_voice:
        return "voice_file"
    mime = mime_type or (mimetypes.guess_type(file_name or "")[0] if file_name else None) or "application/octet-stream"
    if mime.startswith("image/"):
        return "image_file"
    if mime.startswith("video/"):
        return "video_file"
    return "file_file"


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
    force_voice: bool = False,
    encode_type: int | None = None,
    bits_per_sample: int | None = None,
    sample_rate: int | None = None,
    playtime: int | None = None,
) -> str:
    payload = Path(file_path).read_bytes()
    return await send_binary_file(
        driver,
        api_root=api_root,
        token=token,
        cdn_base_url=cdn_base_url,
        to_user_id=to_user_id,
        context_token=context_token,
        data=payload,
        media_kind=infer_media_kind(file_path, None, force_voice=force_voice),
        file_name=Path(file_path).name,
        text=text,
        encode_type=encode_type,
        bits_per_sample=bits_per_sample,
        sample_rate=sample_rate,
        playtime=playtime,
    )


async def send_binary_file(
    driver,
    *,
    api_root: str,
    token: str,
    cdn_base_url: str,
    to_user_id: str,
    context_token: str | None,
    data: bytes | BytesIO | Path,
    media_kind: str,
    file_name: str | None = None,
    text: str = "",
    encode_type: int | None = None,
    bits_per_sample: int | None = None,
    sample_rate: int | None = None,
    playtime: int | None = None,
) -> str:
    payload, inferred_file_name = normalize_binary_file(data)
    default_name = {
        "image_file": "image.bin",
        "voice_file": "voice.silk",
        "file_file": "file.bin",
        "video_file": "video.mp4",
    }.get(media_kind, "file.bin")
    actual_file_name = file_name or inferred_file_name or default_name

    if media_kind == "image_file":
        uploaded = await upload_media_to_cdn(
            driver=driver,
            api_root=api_root,
            token=token,
            cdn_base_url=cdn_base_url,
            payload=payload,
            to_user_id=to_user_id,
            media_type=UPLOAD_MEDIA_TYPE_IMAGE,
        )
        media_item = build_image_item(uploaded)
    elif media_kind == "voice_file":
        uploaded = await upload_media_to_cdn(
            driver=driver,
            api_root=api_root,
            token=token,
            cdn_base_url=cdn_base_url,
            payload=payload,
            to_user_id=to_user_id,
            media_type=UPLOAD_MEDIA_TYPE_VOICE,
        )
        media_item = build_voice_item(
            uploaded,
            text,
            encode_type=encode_type,
            bits_per_sample=bits_per_sample,
            sample_rate=sample_rate,
            playtime=playtime,
        )
    elif media_kind == "video_file":
        uploaded = await upload_media_to_cdn(
            driver=driver,
            api_root=api_root,
            token=token,
            cdn_base_url=cdn_base_url,
            payload=payload,
            to_user_id=to_user_id,
            media_type=UPLOAD_MEDIA_TYPE_VIDEO,
        )
        media_item = build_video_item(uploaded)
    else:
        uploaded = await upload_media_to_cdn(
            driver=driver,
            api_root=api_root,
            token=token,
            cdn_base_url=cdn_base_url,
            payload=payload,
            to_user_id=to_user_id,
            media_type=UPLOAD_MEDIA_TYPE_FILE,
        )
        media_item = build_file_item(uploaded, actual_file_name)

    if text and media_kind != "voice_file":
        await send_text_message(
            driver,
            api_root=api_root,
            token=token,
            to_user_id=to_user_id,
            context_token=context_token,
            text=text,
        )
    return await send_media_item(
        driver,
        api_root=api_root,
        token=token,
        to_user_id=to_user_id,
        context_token=context_token,
        media_item=media_item,
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
                caption = str(data.get("text", ""))
                if "://" in media_value:
                    remote_payload, remote_file_name = await download_remote_media(driver, media_value)
                    last_message_id = await send_binary_file(
                        driver,
                        api_root=api_root,
                        token=token,
                        cdn_base_url=cdn_base_url,
                        to_user_id=to_user_id,
                        context_token=context_token,
                        data=remote_payload,
                        media_kind=infer_media_kind(remote_file_name, None, force_voice=segment_type == "voice"),
                        file_name=remote_file_name,
                        text=caption,
                        encode_type=data.get("encode_type"),
                        bits_per_sample=data.get("bits_per_sample"),
                        sample_rate=data.get("sample_rate"),
                        playtime=data.get("playtime"),
                    )
                else:
                    last_message_id = await send_media_file(
                        driver,
                        api_root=api_root,
                        token=token,
                        cdn_base_url=cdn_base_url,
                        to_user_id=to_user_id,
                        context_token=context_token,
                        file_path=media_value,
                        text=caption,
                        force_voice=segment_type == "voice",
                        encode_type=data.get("encode_type"),
                        bits_per_sample=data.get("bits_per_sample"),
                        sample_rate=data.get("sample_rate"),
                        playtime=data.get("playtime"),
                    )
                continue

            if segment_type in {"image_file", "voice_file", "file_file", "video_file"}:
                binary_data = data.get("content")
                if binary_data is None:
                    raise ValueError(f"{segment_type} segment missing data")
                caption = str(data.get("text", ""))
                last_message_id = await send_binary_file(
                    driver,
                    api_root=api_root,
                    token=token,
                    cdn_base_url=cdn_base_url,
                    to_user_id=to_user_id,
                    context_token=context_token,
                    data=binary_data,
                    media_kind=segment_type,
                    file_name=data.get("file_name"),
                    text=caption,
                    encode_type=data.get("encode_type"),
                    bits_per_sample=data.get("bits_per_sample"),
                    sample_rate=data.get("sample_rate"),
                    playtime=data.get("playtime"),
                )
                continue

            raise ValueError(f"unsupported segment type: {segment_type}")
    finally:
        pass

    return last_message_id
