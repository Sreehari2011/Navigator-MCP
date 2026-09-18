"""Coherent browser fingerprint profiles.

A fingerprint is only convincing when *everything agrees*: the user-agent, the
``sec-ch-ua`` client hints, platform, screen dimensions, timezone and locale
must all describe the same machine. Each profile below is a self-consistent
bundle applied at context creation so that JS probes and HTTP headers cannot
contradict each other.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Fingerprint:
    name: str
    user_agent: str
    platform: str  # navigator.platform
    sec_ch_ua: str  # matches the UA brand order
    viewport: dict  # window size
    screen: dict  # screen.width/height/avail
    locale: str
    timezone: str
    color_depth: int = 24
    hardware_concurrency: int = 8
    device_memory_gb: int = 8
    webgl_vendor: str = "Intel Inc."
    webgl_renderer: str = "Intel Iris OpenGL Engine"

    def with_overrides(self, **kw) -> Fingerprint:
        return replace(self, **kw)

    def context_kwargs(self) -> dict:
        """Playwright ``new_context`` kwargs implementing this fingerprint."""
        return {
            "user_agent": self.user_agent,
            "viewport": self.viewport,
            "screen": self.screen,
            "locale": self.locale,
            "timezone_id": self.timezone,
            "color_scheme": "light",
            "extra_http_headers": {
                "sec-ch-ua": self.sec_ch_ua,
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": self.platform_title(),
                "accept-language": f"{self.locale},en;q=0.9",
            },
        }

    def platform_title(self) -> str:
        return {
            "Win32": "Windows",
            "MacIntel": "macOS",
            "Linux x86_64": "Linux",
        }.get(self.platform, "Windows")

    @staticmethod
    def minimal(user_agent: str) -> Fingerprint:
        return FINGERPRINTS[0].with_overrides(
            name="custom", user_agent=user_agent
        )


def _win_chrome(major: int, build: int) -> dict:
    return {
        "user_agent": (
            f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"
        ),
        "platform": "Win32",
        "sec_ch_ua": (
            f'"Chromium";v="{major}", "Not?A_Brand";v="24", '
            f'"Google Chrome";v="{major}"'
        ),
        "viewport": {"width": 1536, "height": 824},
        "screen": {"width": 1536, "height": 864},
        "locale": "en-US",
        "timezone": "America/New_York",
    }


def _mac_chrome(major: int) -> dict:
    return {
        "user_agent": (
            f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"
        ),
        "platform": "MacIntel",
        "sec_ch_ua": (
            f'"Chromium";v="{major}", "Not?A_Brand";v="24", '
            f'"Google Chrome";v="{major}"'
        ),
        "viewport": {"width": 1512, "height": 874},
        "screen": {"width": 1512, "height": 982},
        "locale": "en-US",
        "timezone": "America/Chicago",
    }


def _linux_chrome(major: int) -> dict:
    return {
        "user_agent": (
            f"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"
        ),
        "platform": "Linux x86_64",
        "sec_ch_ua": f'"Chromium";v="{major}", "Not;A=Brand";v="99"',
        "viewport": {"width": 1440, "height": 824},
        "screen": {"width": 1920, "height": 1080},
        "locale": "en-US",
        "timezone": "America/Denver",
    }


def _mac_safari() -> dict:
    return {
        "user_agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/17.4 Safari/605.1.15"
        ),
        "platform": "MacIntel",
        "sec_ch_ua": "",
        "viewport": {"width": 1410, "height": 900},
        "screen": {"width": 1512, "height": 982},
        "locale": "en-US",
        "timezone": "America/Los_Angeles",
    }


FINGERPRINTS: list[Fingerprint] = [
    Fingerprint(
        name="win-chrome-131",
        webgl_vendor="Google Inc. (NVIDIA)",
        webgl_renderer="ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 (0x00002503) "
        "Direct3D11 vs_5_0 ps_5_0, D3D11)",
        hardware_concurrency=12,
        device_memory_gb=16,
        **_win_chrome(131, 2832),
    ),
    Fingerprint(
        name="win-chrome-129",
        webgl_vendor="Google Inc. (Intel)",
        webgl_renderer="ANGLE (Intel, Intel(R) UHD Graphics 630 "
        "(0x00003E92) Direct3D11 vs_5_0 ps_5_0, D3D11)",
        hardware_concurrency=8,
        device_memory_gb=8,
        **_win_chrome(129, 2681),
    ),
    Fingerprint(
        name="mac-chrome-130",
        webgl_vendor="Google Inc. (Apple)",
        webgl_renderer="ANGLE (Apple, ANGLE Metal Renderer: Apple M1, "
        "Unspecified Version)",
        hardware_concurrency=8,
        device_memory_gb=16,
        **_mac_chrome(130),
    ),
    Fingerprint(
        name="linux-chrome-128",
        webgl_vendor="Google Inc. (Intel)",
        webgl_renderer="ANGLE (Intel, Mesa Intel(R) UHD Graphics 620 "
        "(CML GT2), OpenGL 4.6)",
        hardware_concurrency=8,
        device_memory_gb=8,
        **_linux_chrome(128),
    ),
    Fingerprint(
        name="mac-safari-17",
        webgl_vendor="Apple",
        webgl_renderer="Apple GPU",
        hardware_concurrency=8,
        device_memory_gb=16,
        **_mac_safari(),
    ),
    Fingerprint(
        name="win-chrome-131-uk",
        webgl_vendor="Google Inc. (NVIDIA)",
        webgl_renderer="ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 SUPER "
        "(0x000021C4) Direct3D11 vs_5_0 ps_5_0, D3D11)",
        hardware_concurrency=16,
        device_memory_gb=32,
        locale="en-GB",
        timezone="Europe/London",
        **{k: v for k, v in _win_chrome(131, 2832).items()
           if k not in {"locale", "timezone"}},
    ),
]


FINGERPRINT_INDEX = {f.name: f for f in FINGERPRINTS}


def pick_fingerprint(name: str | None = None) -> Fingerprint:
    """Pick a fingerprint by name, or a random one for the session."""
    if name:
        if name not in FINGERPRINT_INDEX:
            raise ValueError(
                f"unknown fingerprint '{name}'. Available: {sorted(FINGERPRINT_INDEX)}"
            )
        return FINGERPRINT_INDEX[name]
    return random.choice(FINGERPRINTS)
