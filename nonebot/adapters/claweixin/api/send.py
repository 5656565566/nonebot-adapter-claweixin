import base64
import mimetypes
import os
from dataclasses import dataclass
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


@dataclass(slots=True)
class PreparedMedia:
    payload: bytes
    media_kind: str
    file_name: str
    text: str = ""
    mime_type: str | None = None
    encode_type: int | None = None
    bits_per_sample: int | None = None
    sample_rate: int | None = None
    playtime: int | None = None


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


def _default_file_name(media_kind: str) -> str:
    return {
        "image": "image.bin",
        "voice": "voice.silk",
        "file": "file.bin",
        "video": "video.mp4",
    }.get(media_kind, "file.bin")


def infer_media_kind(file_name: str | None, mime_type: str | None, *, force_voice: bool = False) -> str:
    if force_voice:
        return "voice"
    mime = mime_type or (mimetypes.guess_type(file_name or "")[0] if file_name else None) or "application/octet-stream"
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    return "file"


def build_prepared_media(
    *,
    payload: bytes,
    file_name: str | None,
    mime_type: str | None = None,
    text: str = "",
    segment_type: str | None = None,
    encode_type: int | None = None,
    bits_per_sample: int | None = None,
    sample_rate: int | None = None,
    playtime: int | None = None,
) -> PreparedMedia:
    media_kind = segment_type or infer_media_kind(file_name, mime_type)
    actual_file_name = file_name or _default_file_name(media_kind)
    return PreparedMedia(
        payload=payload,
        media_kind=media_kind,
        file_name=actual_file_name,
        text=text,
        mime_type=mime_type,
        encode_type=encode_type,
        bits_per_sample=bits_per_sample,
        sample_rate=sample_rate,
        playtime=playtime,
    )


def prepare_local_media(
    *,
    file_path: str,
    text: str = "",
    force_voice: bool = False,
    encode_type: int | None = None,
    bits_per_sample: int | None = None,
    sample_rate: int | None = None,
    playtime: int | None = None,
) -> PreparedMedia:
    path = Path(file_path)
    return build_prepared_media(
        payload=path.read_bytes(),
        file_name=path.name,
        text=text,
        segment_type="voice" if force_voice else None,
        encode_type=encode_type,
        bits_per_sample=bits_per_sample,
        sample_rate=sample_rate,
        playtime=playtime,
    )


def prepare_segment_media(
    *,
    segment_type: str,
    data: dict[str, Any],
) -> PreparedMedia | None:
    content = data.get("content")
    if isinstance(content, bytes):
        return build_prepared_media(
            payload=content,
            file_name=data.get("file_name"),
            mime_type=data.get("mime_type"),
            text=str(data.get("text", "")),
            segment_type=segment_type,
            encode_type=data.get("encode_type"),
            bits_per_sample=data.get("bits_per_sample"),
            sample_rate=data.get("sample_rate"),
            playtime=data.get("playtime"),
        )

    media = data.get("media") or {}
    if media.get("encrypt_query_param"):
        return None

    media_value = str(data.get("file") or data.get("path") or data.get("url") or "")
    if not media_value:
        raise ValueError(f"{segment_type} segment missing file/path/url/content")

    if "://" in media_value:
        raise ValueError("remote media should be prepared via download flow")

    return prepare_local_media(
        file_path=media_value,
        text=str(data.get("text", "")),
        force_voice=segment_type == "voice",
        encode_type=data.get("encode_type"),
        bits_per_sample=data.get("bits_per_sample"),
        sample_rate=data.get("sample_rate"),
        playtime=data.get("playtime"),
    )


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
    prepared = prepare_local_media(
        file_path=file_path,
        text=text,
        force_voice=force_voice,
        encode_type=encode_type,
        bits_per_sample=bits_per_sample,
        sample_rate=sample_rate,
        playtime=playtime,
    )
    return await send_binary_file(
        driver,
        api_root=api_root,
        token=token,
        cdn_base_url=cdn_base_url,
        to_user_id=to_user_id,
        context_token=context_token,
        data=prepared.payload,
        media_kind=prepared.media_kind,
        file_name=prepared.file_name,
        text=prepared.text,
        encode_type=prepared.encode_type,
        bits_per_sample=prepared.bits_per_sample,
        sample_rate=prepared.sample_rate,
        playtime=prepared.playtime,
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
    actual_file_name = file_name or inferred_file_name or _default_file_name(media_kind)

    if media_kind == "image":
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
    elif media_kind == "voice":
        uploaded = await upload_media_to_cdn(
            driver=driver,
            api_root=api_root,
            token=token,
            cdn_base_url=cdn_base_url,
            payload=payload,
            to_user_id=to_user_id,
            # media_type=UPLOAD_MEDIA_TYPE_VOICE, 暂不可用使用文件替代
            media_type=UPLOAD_MEDIA_TYPE_FILE,
        )
        """
        resolved_sample_rate = sample_rate
        resolved_bits_per_sample = bits_per_sample
        if resolved_sample_rate is None and actual_file_name.lower().endswith(".silk"):
            resolved_sample_rate = 24000
        if resolved_bits_per_sample is None and actual_file_name.lower().endswith(".silk"):
            resolved_bits_per_sample = 16
        media_item = build_voice_item(
            uploaded,
            text,
            encode_type=encode_type,
            bits_per_sample=resolved_bits_per_sample,
            sample_rate=resolved_sample_rate,
            playtime=playtime,
        )
        """
        media_item = build_file_item(uploaded, actual_file_name)
    elif media_kind == "video":
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

    if text and media_kind != "voice":
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
                media_value = str(data.get("file") or data.get("path") or data.get("url") or "")
                if "://" in media_value:
                    remote_payload, remote_file_name = await download_remote_media(driver, media_value)
                    prepared = build_prepared_media(
                        payload=remote_payload,
                        file_name=remote_file_name,
                        text=str(data.get("text", "")),
                        segment_type=segment_type,
                        encode_type=data.get("encode_type"),
                        bits_per_sample=data.get("bits_per_sample"),
                        sample_rate=data.get("sample_rate"),
                        playtime=data.get("playtime"),
                    )
                else:
                    prepared = prepare_segment_media(segment_type=segment_type, data=data)
                    if prepared is None:
                        continue

                last_message_id = await send_binary_file(
                    driver,
                    api_root=api_root,
                    token=token,
                    cdn_base_url=cdn_base_url,
                    to_user_id=to_user_id,
                    context_token=context_token,
                    data=prepared.payload,
                    media_kind=prepared.media_kind,
                    file_name=prepared.file_name,
                    text=prepared.text,
                    encode_type=prepared.encode_type,
                    bits_per_sample=prepared.bits_per_sample,
                    sample_rate=prepared.sample_rate,
                    playtime=prepared.playtime,
                )
                continue

            raise ValueError(f"unsupported segment type: {segment_type}")
    finally:
        pass

    return last_message_id
