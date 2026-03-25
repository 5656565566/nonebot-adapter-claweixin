import hashlib
from dataclasses import dataclass
from typing import Any, Optional

from nonebot.drivers import HTTPClientMixin

from .cdn.download import download_and_decrypt_buffer, download_plain_cdn_buffer
from .mime import get_mime_type

MESSAGE_ITEM_TYPE_IMAGE = 2
MESSAGE_ITEM_TYPE_VOICE = 3
MESSAGE_ITEM_TYPE_FILE = 4
MESSAGE_ITEM_TYPE_VIDEO = 5


@dataclass(slots=True)
class InboundMediaResult:
    media_data: Optional[bytes] = None
    media_type: Optional[str] = None
    file_name: Optional[str] = None

async def download_media_from_item(
    driver: HTTPClientMixin,
    *,
    item: dict[str, Any],
    cdn_base_url: str,
) -> InboundMediaResult:
    result = InboundMediaResult()
    item_type = item.get("type")

    if item_type == MESSAGE_ITEM_TYPE_IMAGE:
        image_item = item.get("image_item") or {}
        media = image_item.get("media") or {}
        encrypted_query_param = media.get("encrypt_query_param")
        aes_key = image_item.get("aeskey") or media.get("aes_key")
        if not encrypted_query_param:
            return result
        if aes_key and len(str(aes_key)) == 32 and all(ch in "0123456789abcdefABCDEF" for ch in str(aes_key)):
            import base64
            aes_key = base64.b64encode(bytes.fromhex(str(aes_key))).decode()
        payload = (
            await download_and_decrypt_buffer(driver, str(encrypted_query_param), str(aes_key), cdn_base_url)
            if aes_key
            else await download_plain_cdn_buffer(driver, str(encrypted_query_param), cdn_base_url)
        )
        mime_type = get_mime_type(payload)
        suffix = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/bmp": ".bmp",
            "image/x-icon": ".ico",
            "image/tiff": ".tiff",
            "image/pcx": ".pcx",
        }.get(mime_type, ".bin")
        file_id = hashlib.md5(payload).hexdigest()
        result.file_name = f"image-{file_id}{suffix}"
        result.media_data = payload
        result.media_type = mime_type
        return result

    if item_type == MESSAGE_ITEM_TYPE_VOICE:
        voice_item = item.get("voice_item") or {}
        media = voice_item.get("media") or {}
        encrypted_query_param = media.get("encrypt_query_param")
        aes_key = media.get("aes_key")
        if not encrypted_query_param or not aes_key:
            return result
        payload = await download_and_decrypt_buffer(driver, str(encrypted_query_param), str(aes_key), cdn_base_url)
        file_id = hashlib.md5(payload).hexdigest()
        result.file_name = f"{file_id}.silk"
        result.media_data = payload
        result.media_type = "audio/silk"
        return result

    if item_type == MESSAGE_ITEM_TYPE_FILE:
        file_item = item.get("file_item") or {}
        media = file_item.get("media") or {}
        encrypted_query_param = media.get("encrypt_query_param")
        aes_key = media.get("aes_key")
        file_name = str(file_item.get("file_name") or "file.bin")
        if not encrypted_query_param or not aes_key:
            return result
        payload = await download_and_decrypt_buffer(driver, str(encrypted_query_param), str(aes_key), cdn_base_url)
        mime_type = get_mime_type(payload)
        suffix = {
            "application/pdf": ".pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
            "application/zip": ".zip",
            "application/vnd.ms-office": ".doc",
            "application/rtf": ".rtf",
            "application/gzip": ".gz",
            "application/x-bzip2": ".bz2",
            "application/x-xz": ".xz",
            "application/vnd.rar": ".rar",
            "application/x-7z-compressed": ".7z",
            "application/x-msdownload": ".exe",
            "application/x-executable": ".elf",
            "application/xml": ".xml",
            "text/html": ".html",
            "text/plain": ".txt",
            "application/x-font-ttf": ".ttf",
            "application/x-font": ".fon",
            "application/octet-stream": ".bin",
        }.get(mime_type)
        if suffix is None:
            suffix = ".bin"
        file_id = hashlib.md5(payload).hexdigest()
        result.file_name = f"{file_id}{suffix}"
        result.media_data = payload
        result.media_type = mime_type
        return result

    if item_type == MESSAGE_ITEM_TYPE_VIDEO:
        video_item = item.get("video_item") or {}
        media = video_item.get("media") or {}
        encrypted_query_param = media.get("encrypt_query_param")
        aes_key = media.get("aes_key")
        if not encrypted_query_param or not aes_key:
            return result
        payload = await download_and_decrypt_buffer(driver, str(encrypted_query_param), str(aes_key), cdn_base_url)
        file_id = hashlib.md5(payload).hexdigest()
        result.file_name = f"{file_id}.mp4"
        result.media_data = payload
        result.media_type = "video/mp4"
        return result

    return result


async def download_media_from_message(
    driver: HTTPClientMixin,
    *,
    item_list: list[dict[str, Any]],
    cdn_base_url: str,
) -> InboundMediaResult:
    for item in item_list:
        result = await download_media_from_item(driver, item=item, cdn_base_url=cdn_base_url)
        if result.media_data is not None:
            return result
    return InboundMediaResult()
