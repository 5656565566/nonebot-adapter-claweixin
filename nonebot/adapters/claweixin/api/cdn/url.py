from urllib.parse import urlencode


def ensure_trailing_slash(url: str) -> str:
    return url if url.endswith("/") else f"{url}/"


def build_cdn_download_url(encrypted_query_param: str, cdn_base_url: str) -> str:
    base = ensure_trailing_slash(cdn_base_url).rstrip("/")
    query = urlencode({"encrypted_query_param": encrypted_query_param})
    return f"{base}/download?{query}"
