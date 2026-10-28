# -*- coding: utf-8 -*-
"""
动作提取与动作向导网格合成器 (Motion Extractor & Guide Sheet Builder)
从现有的 GIF、WebP 或 MP4 视频中均匀采样 9 帧 (3x3) 或 16 帧 (4x4)，
拼合为标准动作向导图，用于驱动目标角色生成同款动作的实况照片。
"""

import os
from typing import List
from PIL import Image
import numpy as np


def extract_frames_from_media(media_path: str, num_frames: int = 9) -> List[Image.Image]:
    """从动图 (.gif, .webp) 或视频 (.mp4, .mov 等) 中均匀采样指定帧数"""
    if not os.path.isfile(media_path):
        raise FileNotFoundError(f"未找到源动作媒体文件: {media_path}")

    ext = os.path.splitext(media_path)[1].lower()
    raw_frames: List[Image.Image] = []

    if ext in (".gif", ".webp", ".png", ".apng"):
        im = Image.open(media_path)
        n_frames = getattr(im, "n_frames", 1)
        for i in range(n_frames):
            im.seek(i)
            bg = Image.new("RGB", im.size, (255, 255, 255))
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                rgba = im.convert("RGBA")
                bg.paste(rgba, mask=rgba.split()[-1])
            else:
                bg.paste(im.convert("RGB"))
            raw_frames.append(bg)
    else:
        import imageio.v3 as iio
        for frame_arr in iio.imiter(media_path):
            raw_frames.append(Image.fromarray(frame_arr).convert("RGB"))

    if not raw_frames:
        raise ValueError(f"无法从媒体文件中提取帧: {media_path}")

    indices = np.linspace(0, len(raw_frames) - 1, num_frames, dtype=int)
    return [raw_frames[idx] for idx in indices]


def create_motion_guide_grid(
    media_path: str,
    output_path: str,
    grid: str = "3x3",
    cell_size: int = 340,
    border: int = 4,
) -> str:
    """将提取的帧拼合为 3x3 或 4x4 动作参考网格图"""
    is_16 = "4" in str(grid) or str(grid) == "16"
    rows = 4 if is_16 else 3
    cols = 4 if is_16 else 3
    total = rows * cols

    frames = extract_frames_from_media(media_path, num_frames=total)
    grid_w = cols * cell_size + (cols - 1) * border
    grid_h = rows * cell_size + (rows - 1) * border
    canvas = Image.new("RGB", (grid_w, grid_h), (255, 255, 255))

    for idx, frame in enumerate(frames):
        r = idx // cols
        c = idx % cols
        w, h = frame.size
        min_dim = min(w, h)
        left = (w - min_dim) // 2
        top = (h - min_dim) // 2
        sq = frame.crop((left, top, left + min_dim, top + min_dim)).resize(
            (cell_size, cell_size), Image.Resampling.LANCZOS
        )
        x = c * (cell_size + border)
        y = r * (cell_size + border)
        canvas.paste(sq, (x, y))

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    canvas.save(output_path, quality=95)
    return output_path
