from io import BytesIO
from pathlib import Path
from typing import Any, Type, Iterable, Optional, Union
from typing_extensions import override

from nonebot.adapters import Message as BaseMessage, MessageSegment as BaseMessageSegment


class MessageSegment(BaseMessageSegment["Message"]):
    """
    ClaWeixin 协议 MessageSegment 适配
    依据 OpenClaw WeChat 协议定义 支持 TEXT, IMAGE, VOICE, FILE, VIDEO 等
    同时支持本地二进制媒体段 IMAGE_FILE, VOICE_FILE, FILE_FILE, VIDEO_FILE
    """

    @classmethod
    @override
    def get_message_class(cls) -> Type["Message"]:
        return Message

    @override
    def __str__(self) -> str:
        if self.is_text():
            return self.data.get("text", "")
        return f"[{self.type}:{self.data}]"

    @override
    def is_text(self) -> bool:
        return self.type == "text"

    @staticmethod
    def text(text: str) -> "Text":
        return Text("text", {"text": text})

    @staticmethod
    def image(
        url: Optional[str] = None,
        media: Optional[dict] = None,
        aeskey: Optional[str] = None
    ) -> "Image":
        data = {}
        if url:
            data["url"] = url
        if media:
            data["media"] = media
        if aeskey:
            data["aeskey"] = aeskey
        return Image("image", data)

    @staticmethod
    def image_file(data: Union[bytes, BytesIO, Path], file_name: Optional[str] = None) -> "LocalAttachment":
        return LocalAttachment.image(data, file_name)

    @staticmethod
    def voice(
        url: Optional[str] = None,
        text: Optional[str] = None,
        media: Optional[dict] = None,
    ) -> "Voice":
        data = {}
        if url:
            data["url"] = url
        if text:
            data["text"] = text
        if media:
            data["media"] = media
        return Voice("voice", data)

    @staticmethod
    def voice_file(
        data: Union[bytes, BytesIO, Path],
        file_name: Optional[str] = None,
        text: Optional[str] = None,
        encode_type: int = 6,
        bits_per_sample: Optional[int] = None,
        sample_rate: Optional[int] = None,
        playtime: Optional[int] = None,
    ) -> "LocalAttachment":
        return LocalAttachment.voice(data, file_name, text, encode_type, bits_per_sample, sample_rate, playtime)

    @staticmethod
    def file(
        url: Optional[str] = None, 
        file_name: Optional[str] = None,
        media: Optional[dict] = None
    ) -> "File":
        data = {}
        if file_name:
            data["file_name"] = file_name
        if url:
            data["url"] = url
        if media:
            data["media"] = media
        return File("file", data)

    @staticmethod
    def file_file(data: Union[bytes, BytesIO, Path], file_name: Optional[str] = None) -> "LocalAttachment":
        return LocalAttachment.file(data, file_name)

    @staticmethod
    def video(url: Optional[str] = None, media: Optional[dict] = None) -> "Video":
        data = {}
        if url:
            data["url"] = url
        if media:
            data["media"] = media
        return Video("video", data)

    @staticmethod
    def video_file(data: Union[bytes, BytesIO, Path], file_name: Optional[str] = None) -> "LocalAttachment":
        return LocalAttachment.video(data, file_name)


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


class LocalAttachment(MessageSegment):
    @staticmethod
    def _build(type_: str, data: Union[bytes, BytesIO, Path], file_name: Optional[str] = None, text: Optional[str] = None) -> "LocalAttachment":
        payload: bytes
        inferred_file_name: Optional[str] = None
        if isinstance(data, BytesIO):
            payload = data.getvalue()
        elif isinstance(data, Path):
            payload = data.read_bytes()
            inferred_file_name = data.name
        else:
            payload = data
        file_data: dict[str, Any] = {"content": payload}
        if file_name:
            file_data["file_name"] = file_name
        elif inferred_file_name:
            file_data["file_name"] = inferred_file_name
        if text:
            file_data["text"] = text
        return LocalAttachment(type_, file_data)

    @staticmethod
    def image(data: Union[bytes, BytesIO, Path], file_name: Optional[str] = None) -> "LocalAttachment":
        return LocalAttachment._build("image_file", data, file_name)

    @staticmethod
    def voice(
        data: Union[bytes, BytesIO, Path],
        file_name: Optional[str] = None,
        text: Optional[str] = None,
        encode_type: int = 6,
        bits_per_sample: Optional[int] = None,
        sample_rate: Optional[int] = None,
        playtime: Optional[int] = None,
    ) -> "LocalAttachment":
        attachment = LocalAttachment._build("voice_file", data, file_name, text)
        attachment.data["encode_type"] = encode_type
        if bits_per_sample is not None:
            attachment.data["bits_per_sample"] = bits_per_sample
        if sample_rate is not None:
            attachment.data["sample_rate"] = sample_rate
        if playtime is not None:
            attachment.data["playtime"] = playtime
        return attachment

    @staticmethod
    def file(data: Union[bytes, BytesIO, Path], file_name: Optional[str] = None) -> "LocalAttachment":
        return LocalAttachment._build("file_file", data, file_name)

    @staticmethod
    def video(data: Union[bytes, BytesIO, Path], file_name: Optional[str] = None) -> "LocalAttachment":
        return LocalAttachment._build("video_file", data, file_name)

    @override
    def __str__(self) -> str:
        if self.type == "image_file":
            return "[待发送的图片]"
        if self.type == "voice_file":
            return "[待发送的语音]"
        if self.type == "video_file":
            return "[待发送的视频]"
        return "[待发送的文件]"


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
    def from_message_items(cls, items: list[dict]) -> "Message":
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
        for item in items:
            item_type = item.get("type")
            if item_type == 1 and "text_item" in item:
                msg.append(MessageSegment.text(item["text_item"].get("text", "")))
            elif item_type == 2 and "image_item" in item:
                img_data = item["image_item"]
                msg.append(MessageSegment.image(
                    url=img_data.get("url"),
                    media=img_data.get("media"),
                    aeskey=img_data.get("aeskey")
                ))
            elif item_type == 3 and "voice_item" in item:
                voice_data = item["voice_item"]
                msg.append(MessageSegment.voice(
                    text=voice_data.get("text"),
                    media=voice_data.get("media")
                ))
            elif item_type == 4 and "file_item" in item:
                file_data = item["file_item"]
                msg.append(MessageSegment.file(
                    file_name=file_data.get("file_name"),
                    media=file_data.get("media")
                ))
            elif item_type == 5 and "video_item" in item:
                video_data = item["video_item"]
                msg.append(MessageSegment.video(
                    media=video_data.get("media")
                ))
        return msg
