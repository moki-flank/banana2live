# -*- coding: utf-8 -*-
"""
自适应宫格切片器 (Adaptive Grid Slicer)
支持 3x3 (9帧) 与 4x4 (16帧) 宫格大图精确中心切分，兼容 1K / 2K / 4K (4096x4096) 分辨率。
"""

import os
from typing import List, Optional, Union
from PIL import Image
from .matting import remove_background


def slice_grid(
    image_input: Union[str, Image.Image],
    output_dir: Optional[str] = None,
    grid_layout: str = "3x3",
    crop_size: Optional[int] = None,
    export_size: Optional[int] = None,
    transparent: bool = False,
) -> List[Image.Image]:
    """
    将 3x3 或 4x4 宫格大图切分为连续对齐的单帧序列。
    默认采用 93.75% 单元格中心安全区内缩裁切，彻底避开网格分割线。
    """
    if isinstance(image_input, str):
        im = Image.open(image_input).convert("RGB")
    else:
        im = image_input.convert("RGB")

    width, height = im.size
    is_16 = "4" in str(grid_layout) or str(grid_layout) == "16"
    rows = 4 if is_16 else 3
    cols = 4 if is_16 else 3

    step_x = width / float(cols)
    step_y = height / float(rows)

    cell_centers_x = [step_x * (c + 0.5) for c in range(cols)]
    cell_centers_y = [step_y * (r + 0.5) for r in range(rows)]

    if crop_size is None:
        crop_size = int(round(min(step_x, step_y) * 0.9375))
    # 保证偶数宽高以便 H.264 (yuv420p) 视频编码
    if crop_size % 2 != 0:
        crop_size -= 1

    crop_half = crop_size // 2
    frames: List[Image.Image] = []

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    frame_idx = 1
    for r in range(rows):
        for c in range(cols):
            cx = cell_centers_x[c]
            cy = cell_centers_y[r]

            x0 = int(round(cx - crop_half))
            y0 = int(round(cy - crop_half))
            x0 = max(0, min(width - crop_size, x0))
            y0 = max(0, min(height - crop_size, y0))
            x1 = x0 + crop_size
            y1 = y0 + crop_size

            frame = im.crop((x0, y0, x1, y1))

            if transparent:
                frame = remove_background(frame)

            if export_size and export_size > 0:
                target_sz = export_size if export_size % 2 == 0 else export_size - 1
                if frame.width != target_sz or frame.height != target_sz:
                    frame = frame.resize((target_sz, target_sz), Image.Resampling.LANCZOS)

            frames.append(frame)

            if output_dir:
                save_path = os.path.join(output_dir, f"frame_{frame_idx:02d}.png")
                frame.save(save_path)

            frame_idx += 1

    return frames
