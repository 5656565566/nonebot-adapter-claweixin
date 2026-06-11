import re
from importlib.metadata import PackageNotFoundError, version
from typing import Optional

DEFAULT_CHANNEL_VERSION = "0.1.10"
DEFAULT_ILINK_APP_ID = "bot"
DEFAULT_BOT_AGENT = "nonebot-adapter-claweixin"
BOT_AGENT_MAX_LEN = 256


def get_channel_version() -> str:
    try:
        return version("nonebot-adapter-claweixin")
    except PackageNotFoundError:
        return DEFAULT_CHANNEL_VERSION


def build_client_version(version_text: str) -> int:
    parts = version_text.split(".")
    major = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
    minor = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    patch = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    return ((major & 0xFF) << 16) | ((minor & 0xFF) << 8) | (patch & 0xFF)


def sanitize_bot_agent(raw: Optional[str]) -> str:
    if not raw or not isinstance(raw, str):
        return DEFAULT_BOT_AGENT

    product_re = re.compile(r"^[A-Za-z0-9_.-]{1,32}/[A-Za-z0-9_.+-]{1,32}$")
    comment_re = re.compile(r"^[\x20-\x27\x2A-\x7E]{1,64}$")
    raw_tokens = raw.strip().split()
    if not raw_tokens:
        return DEFAULT_BOT_AGENT

    tokens: list[str] = []
    index = 0
    while index < len(raw_tokens):
        token = raw_tokens[index]
        if token.startswith("(") and not token.endswith(")"):
            pieces = [token]
            while index + 1 < len(raw_tokens) and not pieces[-1].endswith(")"):
                index += 1
                pieces.append(raw_tokens[index])
            tokens.append(" ".join(pieces))
        else:
            tokens.append(token)
        index += 1

    accepted: list[str] = []
    pending_product: str | None = None
    for token in tokens:
        if token.startswith("(") and token.endswith(")"):
            inner = token[1:-1]
            if pending_product and comment_re.match(inner):
                accepted.append(f"{pending_product} ({inner})")
                pending_product = None
            elif pending_product:
                accepted.append(pending_product)
                pending_product = None
            continue
        if pending_product:
            accepted.append(pending_product)
            pending_product = None
        if product_re.match(token):
            pending_product = token
    if pending_product:
        accepted.append(pending_product)

    if not accepted:
        return DEFAULT_BOT_AGENT

    resolved: list[str] = []
    size = 0
    for token in accepted:
        extra = (1 if resolved else 0) + len(token.encode("utf-8"))
        if size + extra > BOT_AGENT_MAX_LEN:
            break
        resolved.append(token)
        size += extra
    return " ".join(resolved) if resolved else DEFAULT_BOT_AGENT


def build_common_headers(route_tag: Optional[str] = None) -> dict[str, str]:
    headers = {
        "iLink-App-Id": DEFAULT_ILINK_APP_ID,
        "iLink-App-ClientVersion": str(build_client_version(get_channel_version())),
    }
    if route_tag:
        headers["SKRouteTag"] = route_tag
    return headers

