"""Shared utilities: IP extraction and geolocation."""
import ipaddress
import logging
import requests
from fastapi import Request

logger = logging.getLogger(__name__)

_PRIVATE_LABELS = {
    "127.0.0.1": "本机",
    "::1": "本机",
}


def _is_private(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_private
    except ValueError:
        return False


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


def get_ip_location(ip: str) -> str:
    """Return a human-readable location string for a public IP.

    Returns '本机' / '内网' for loopback/private addresses without an API call.
    Returns '' on lookup failure so callers can decide how to display it.
    """
    if not ip or ip == "unknown":
        return ""
    if ip in _PRIVATE_LABELS:
        return _PRIVATE_LABELS[ip]
    if _is_private(ip):
        return "内网"
    try:
        r = requests.get(
            f"http://ip-api.com/json/{ip}",
            params={"lang": "zh-CN", "fields": "status,country,regionName,city"},
            timeout=4,
            # 绕过本机代理(127.0.0.1:7892)——否则 requests 走代理无法到达
            # ip-api.com,会 2s 超时返回空,导致归属地一直为空。
            proxies={"http": None, "https": None},
        )
        data = r.json()
        if data.get("status") == "success":
            parts = [
                data.get("country", ""),
                data.get("regionName", ""),
                data.get("city", ""),
            ]
            return " ".join(p for p in parts if p)
    except Exception as e:
        logger.debug("IP geolocation failed for %s: %s", ip, e)
    return ""
