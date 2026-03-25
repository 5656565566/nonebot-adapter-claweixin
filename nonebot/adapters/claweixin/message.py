from io import BytesIO
from pathlib import Path
from typing import Any, Iterable, Optional, Type, Union

from nonebot.adapters import Message as BaseMessage, MessageSegment as BaseMessageSegment
from typing_extensions import override


class MessageSegment(BaseMessageSegment["Message"]):
    """
    ClaWeixin 协议 MessageSegment 适配
    依据 OpenClaw WeChat 协议定义支持 TEXT, IMAGE, VOICE, FILE, VIDEO
    """

    @classmethod
    @override
    def get_message_class(cls) -> Type["Message"]:
        return Message

    @override
    def __str__(self) -> str:
        if self.is_text():
            return self.data.get("text", "")
        return f"[{self.type}]"

    @override
    def is_text(self) -> bool:
        return self.type == "text"

    @staticmethod
    def text(text: str) -> "Text":
        return Text("text", {"text": text})

    @staticmethod
    def image(
        data: Union[bytes, BytesIO, Path, None] = None,
        *,
        url: Optional[str] = None,
        media: Optional[dict[str, Any]] = None,
        aeskey: Optional[str] = None,
        file_name: Optional[str] = None,
    ) -> "Image":
        payload = _normalize_media_input(data)
        segment_data: dict[str, Any] = {}
        if payload is not None:
            segment_data["content"] = payload[0]
            segment_data["file_name"] = file_name or payload[1]
        if url:
            segment_data["url"] = url
        if media:
            segment_data["media"] = media
        if aeskey:
            segment_data["aeskey"] = aeskey
        return Image("image", segment_data)

    @staticmethod
    def voice(
        data: Union[bytes, BytesIO, Path, None] = None,
        *,
        url: Optional[str] = None,
        text: Optional[str] = None,
        media: Optional[dict[str, Any]] = None,
        file_name: Optional[str] = None,
        encode_type: int = 6,
        bits_per_sample: Optional[int] = None,
        sample_rate: Optional[int] = None,
        playtime: Optional[int] = None,
    ) -> "Voice":
        payload = _normalize_media_input(data)
        segment_data: dict[str, Any] = {}
        if payload is not None:
            segment_data["content"] = payload[0]
            segment_data["file_name"] = file_name or payload[1]
            segment_data["encode_type"] = encode_type
            if bits_per_sample is not None:
                segment_data["bits_per_sample"] = bits_per_sample
            if sample_rate is not None:
                segment_data["sample_rate"] = sample_rate
            if playtime is not None:
                segment_data["playtime"] = playtime
        if url:
            segment_data["url"] = url
        if text:
            segment_data["text"] = text
        if media:
            segment_data["media"] = media
        return Voice("voice", segment_data)

    @staticmethod
    def file(
        data: Union[bytes, BytesIO, Path, None] = None,
        *,
        url: Optional[str] = None,
        file_name: Optional[str] = None,
        media: Optional[dict[str, Any]] = None,
    ) -> "File":
        payload = _normalize_media_input(data)
        segment_data: dict[str, Any] = {}
        if payload is not None:
            segment_data["content"] = payload[0]
            segment_data["file_name"] = file_name or payload[1]
        elif file_name:
            segment_data["file_name"] = file_name
        if url:
            segment_data["url"] = url
        if media:
            segment_data["media"] = media
        return File("file", segment_data)

    @staticmethod
    def video(
        data: Union[bytes, BytesIO, Path, None] = None,
        *,
        url: Optional[str] = None,
        media: Optional[dict[str, Any]] = None,
        file_name: Optional[str] = None,
    ) -> "Video":
        payload = _normalize_media_input(data)
        segment_data: dict[str, Any] = {}
        if payload is not None:
            segment_data["content"] = payload[0]
            segment_data["file_name"] = file_name or payload[1]
        if url:
            segment_data["url"] = url
        if media:
            segment_data["media"] = media
        return Video("video", segment_data)


def _normalize_media_input(data: Union[bytes, BytesIO, Path, None]) -> tuple[bytes, Optional[str]] | None:
    if data is None:
        return None
    if isinstance(data, BytesIO):
        return data.getvalue(), None
    if isinstance(data, Path):
        return data.read_bytes(), data.name
    return data, None


class Text(MessageSegment):
    @override
    def __str__(self) -> str:
        return self.data["text"]


class Image(MessageSegment):
    @override
    def __str__(self) -> str:
        return "[图片]"


class Voice(MessageSegment):
    @override
    def __str__(self) -> str:
        return "[语音]"


class File(MessageSegment):
    @override
    def __str__(self) -> str:
        return "[文件]"


class Video(MessageSegment):
    @override
    def __str__(self) -> str:
        return "[视频]"


class Message(BaseMessage[MessageSegment]):
    """
    ClaWeixin 协议 Message 适配
    """

    @classmethod
    @override
    def get_segment_class(cls) -> Type[MessageSegment]:
        return MessageSegment

    @staticmethod
    @override
    def _construct(msg: str) -> Iterable[MessageSegment]:
        yield MessageSegment.text(msg)

    @classmethod
    def from_message_items(
        cls,
        items: list[dict],
        media_data: bytes | None = None,
        file_name: str | None = None,
    ) -> "Message":
        """
        从 OpenClaw WeChat 的 MessageItem 列表构造 Message
        MessageItemType:
          NONE: 0,
          TEXT: 1,
          IMAGE: 2,
          VOICE: 3,
          FILE: 4,
          VIDEO: 5
        """
        msg = cls()
        media_payload = media_data
        media_file_name = file_name
        for item in items:
            item_type = item.get("type")
            if item_type == 1 and "text_item" in item:
                msg.append(MessageSegment.text(item["text_item"].get("text", "")))
            elif item_type == 2 and "image_item" in item:
                img_data = item["image_item"]
                msg.append(
                    MessageSegment.image(
                        media_payload,
                        url=img_data.get("url"),
                        media=img_data.get("media"),
                        aeskey=img_data.get("aeskey"),
                        file_name=media_file_name,
                    )
                )
                media_payload = None
                media_file_name = None
            elif item_type == 3 and "voice_item" in item:
                voice_data = item["voice_item"]
                msg.append(
                    MessageSegment.voice(
                        media_payload,
                        text=voice_data.get("text"),
                        media=voice_data.get("media"),
                        file_name=media_file_name,
                    )
                )
                media_payload = None
                media_file_name = None
            elif item_type == 4 and "file_item" in item:
                file_data = item["file_item"]
                msg.append(
                    MessageSegment.file(
                        media_payload,
                        url=file_data.get("url"),
                        file_name=file_data.get("file_name") or media_file_name,
                        media=file_data.get("media"),
                    )
                )
                media_payload = None
                media_file_name = None
            elif item_type == 5 and "video_item" in item:
                video_data = item["video_item"]
                msg.append(
                    MessageSegment.video(
                        media_payload,
                        url=video_data.get("url"),
                        media=video_data.get("media"),
                        file_name=media_file_name,
                    )
                )
                media_payload = None
                media_file_name = None
        return msg
