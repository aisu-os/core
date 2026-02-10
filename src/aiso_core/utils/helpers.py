from aiso_core.config import settings


def with_full_url(path_or_url: str | None) -> str | None:
    if not path_or_url:
        return None

    if path_or_url.startswith("http") or path_or_url.startswith("https"):
        return path_or_url

    return f"{settings.app_url.rstrip('/')}{path_or_url}"
