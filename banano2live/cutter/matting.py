# -*- coding: utf-8 -*-
"""
智能去底与实况图背景合成模块 (Alpha Matting & Backdrop Compositor)
采用【外边缘泛洪填充 (Exterior Boundary BFS)】算法：
只扣除与画面边缘相连的纯色/浅色背景，100% 保护角色体内的白色服饰、眼白与高光。
同时支持将去底后的透明序列帧合成到自定义实况照片背景色上。
"""

from collections import deque
from typing import Union, Tuple
from PIL import Image, ImageFilter, ImageColor
import numpy as np


def remove_background(
    image: Union[str, Image.Image],
    bg_threshold: int = 240,
    color_dist: float = 25.0,
    feather_radius: float = 0.5,
) -> Image.Image:
    """智能去除画面外圈纯色/浅色背景，返回 RGBA 图像"""
    if isinstance(image, str):
        im = Image.open(image).convert("RGB")
    else:
        im = image.convert("RGB")

    orig_w, orig_h = im.size
    scale = 1.0
    if max(orig_w, orig_h) > 512:
        scale = 512.0 / max(orig_w, orig_h)
        small_im = im.resize((int(orig_w * scale), int(orig_h * scale)), Image.Resampling.BILINEAR)
    else:
        small_im = im

    arr = np.array(small_im, dtype=np.int32)
    h, w, _ = arr.shape

    corners = [arr[0, 0], arr[0, w - 1], arr[h - 1, 0], arr[h - 1, w - 1]]
    bg_color = np.mean(corners, axis=0)

    mask = np.zeros((h, w), dtype=bool)
    q = deque()

    for x in range(w):
        for y in (0, h - 1):
            if np.linalg.norm(arr[y, x] - bg_color) < color_dist or np.all(arr[y, x] > bg_threshold):
                if not mask[y, x]:
                    mask[y, x] = True
                    q.append((y, x))

    for y in range(h):
        for x in (0, w - 1):
            if np.linalg.norm(arr[y, x] - bg_color) < color_dist or np.all(arr[y, x] > bg_threshold):
                if not mask[y, x]:
                    mask[y, x] = True
                    q.append((y, x))

    while q:
        cy, cx = q.popleft()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ny, nx = cy + dy, cx + dx
            if 0 <= ny < h and 0 <= nx < w and not mask[ny, nx]:
                px = arr[ny, nx]
                if np.linalg.norm(px - bg_color) < color_dist or np.all(px > bg_threshold):
                    mask[ny, nx] = True
                    q.append((ny, nx))

    alpha_arr = np.where(mask, 0, 255).astype(np.uint8)
    alpha_img = Image.fromarray(alpha_arr, mode="L")

    if scale != 1.0:
        alpha_img = alpha_img.resize((orig_w, orig_h), Image.Resampling.BILINEAR)

    if feather_radius > 0:
        alpha_img = alpha_img.filter(ImageFilter.GaussianBlur(radius=feather_radius))

    rgba = im.convert("RGBA")
    rgba.putalpha(alpha_img)
    return rgba


def composite_on_backdrop(
    image: Image.Image,
    backdrop: Union[str, Tuple[int, int, int]] = "#FFFFFF",
) -> Image.Image:
    """将含 Alpha 通道的图像合成到实况照片纯色背景上，返回 RGB 图像"""
    if image.mode != "RGBA":
        return image.convert("RGB")
    if isinstance(backdrop, str):
        try:
            rgb = ImageColor.getrgb(backdrop)
        except Exception:
            rgb = (255, 255, 255)
    else:
        rgb = backdrop
    bg = Image.new("RGBA", image.size, (*rgb[:3], 255))
    bg.alpha_composite(image)
    return bg.convert("RGB")
