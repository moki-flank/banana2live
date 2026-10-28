# -*- coding: utf-8 -*-
"""
banano2live - 全能 AI 实况图 (Live Photo / Motion Photo) 生成与转换引擎
支持纯 Web 前端零安装运行 + HrioAPI SDK 视频直生转实况 + 3x3/4x4 宫格切分转实况 + 本地视频/图片离线合成实况。
"""

__version__ = "1.0.0"

from .core import Banano2Live, banano2live
from .sdk.client import (
    HrioClient,
    HrioAPIError,
    DEFAULT_BASE_URL,
    OFFICIAL_WEBSITE,
    DEFAULT_IMAGE_MODEL,
    DEFAULT_VIDEO_MODEL,
)
from .cutter.livephoto_builder import (
    build_google_motion_photo,
    build_apple_livephoto_zip,
    build_livephoto_bundle,
    inspect_motion_photo,
)

__all__ = [
    "Banano2Live",
    "banano2live",
    "HrioClient",
    "HrioAPIError",
    "DEFAULT_BASE_URL",
    "OFFICIAL_WEBSITE",
    "DEFAULT_IMAGE_MODEL",
    "DEFAULT_VIDEO_MODEL",
    "build_google_motion_photo",
    "build_apple_livephoto_zip",
    "build_livephoto_bundle",
    "inspect_motion_photo",
]
