# -*- coding: utf-8 -*-
"""
实况图视频流合成与裁剪引擎 (Video Synthesizer & Lossless Trimmer)
核心能力：
  1. 将 3x3 (9帧) / 4x4 (16帧) 宫格切分出的序列帧合成为高画质 H.264 MP4/MOV 实况视频流
     - 支持乒乓往返循环 (Ping-Pong) 与正序循环 (Loop)
     - 支持帧间平滑插值 (Crossfade Blending)，让 9/16 帧拥有 24~30fps 的丝滑实况质感
     - 自动补齐至实况图黄金时长 (2.0s ~ 3.0s)
     - 支持混入自定义环境音/背景音乐音轨
  2. 处理 AI 生成视频或本地视频：
     - 未剪辑时直接保留原始视频流与原声（零画质损耗，对齐 W4J1e/Video2LivePhoto）
     - 剪辑时通过内置 FFmpeg 精准截取指定时间段并保留 AAC 原始音频轨道
  3. 自动从视频任意时间点提取高画质 JPEG 实况封面帧
"""

import os
import shutil
import subprocess
from typing import List, Optional, Union, Tuple
from PIL import Image
import numpy as np

from .matting import composite_on_backdrop


def _get_ffmpeg_exe() -> Optional[str]:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg")


def build_gif_or_webp(
    frames: List[Union[str, Image.Image]],
    output_path: str,
    duration_ms: int = 140,
    loop: int = 0,
) -> str:
    """将序列帧导出为附属 GIF 或 WebP 预览动图（支持 RGBA 透明通道）"""
    if not frames:
        raise ValueError("帧列表为空")

    loaded: List[Image.Image] = []
    has_alpha = False
    for f in frames:
        im = Image.open(f) if isinstance(f, str) else f
        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
            has_alpha = True
            loaded.append(im.convert("RGBA"))
        else:
            loaded.append(im.convert("RGB"))

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    if output_path.lower().endswith(".webp"):
        loaded[0].save(
            output_path,
            format="WEBP",
            save_all=True,
            append_images=loaded[1:],
            duration=duration_ms,
            loop=loop,
            lossless=True,
        )
        return output_path

    if has_alpha:
        gif_frames = []
        for img in loaded:
            alpha = img.split()[-1]
            p_img = img.convert("RGB").convert("P", palette=Image.Palette.ADAPTIVE, colors=255)
            mask = Image.eval(alpha, lambda a: 255 if a < 128 else 0)
            p_img.paste(255, mask)
            p_img.info["transparency"] = 255
            gif_frames.append(p_img)
        gif_frames[0].save(
            output_path,
            format="GIF",
            save_all=True,
            append_images=gif_frames[1:],
            duration=duration_ms,
            loop=loop,
            disposal=2,
            transparency=255,
            optimize=False,
        )
    else:
        loaded[0].save(
            output_path,
            format="GIF",
            save_all=True,
            append_images=loaded[1:],
            duration=duration_ms,
            loop=loop,
            optimize=True,
        )
    return output_path


def frames_to_mp4(
    frames: List[Union[str, Image.Image]],
    output_mp4_path: str,
    fps: int = 16,
    min_duration_sec: float = 3.0,
    loop_mode: str = "pingpong",
    crossfade_steps: int = 1,
    backdrop: str = "#FFFFFF",
    audio_path: Optional[str] = None,
) -> str:
    """
    将 3x3 (9帧) 或 4x4 (16帧) 切片序列合成为标准 H.264 MP4 实况视频流。
    - loop_mode: "pingpong" (1..N..2 往返无缝循环) 或 "loop" (1..N 重复循环)
    - crossfade_steps: 相邻关键帧之间插入的线性过渡帧数（默认 1，使帧率翻倍更顺滑）
    - min_duration_sec: 实况照片推荐时长 2.0~3.0 秒，自动循环补足时长
    """
    if not frames:
        raise ValueError("帧序列为空，无法合成实况视频")

    rgb_frames: List[Image.Image] = []
    for f in frames:
        im = Image.open(f) if isinstance(f, str) else f
        rgb = composite_on_backdrop(im, backdrop=backdrop)
        # 确保宽高为偶数（H.264 yuv420p 要求）
        w, h = rgb.size
        even_w = w if w % 2 == 0 else w - 1
        even_h = h if h % 2 == 0 else h - 1
        if (even_w, even_h) != (w, h):
            rgb = rgb.resize((even_w, even_h), Image.Resampling.LANCZOS)
        rgb_frames.append(rgb)

    # 构建基础单周期序列
    if loop_mode == "pingpong" and len(rgb_frames) > 2:
        cycle_frames = rgb_frames + rgb_frames[-2:0:-1]
    else:
        cycle_frames = list(rgb_frames)

    # 帧间过渡插值 (Crossfade Blending)
    if crossfade_steps > 0 and len(cycle_frames) > 1:
        interpolated: List[Image.Image] = []
        n = len(cycle_frames)
        for i in range(n):
            f_curr = cycle_frames[i]
            f_next = cycle_frames[(i + 1) % n]
            interpolated.append(f_curr)
            for step in range(1, crossfade_steps + 1):
                alpha = step / float(crossfade_steps + 1)
                blended = Image.blend(f_curr, f_next, alpha)
                interpolated.append(blended)
        cycle_frames = interpolated

    # 计算补足实况图最小时长所需的总帧数
    target_total_frames = max(len(cycle_frames), int(round(fps * min_duration_sec)))
    final_sequence: List[np.ndarray] = []
    while len(final_sequence) < target_total_frames:
        for fr in cycle_frames:
            final_sequence.append(np.asarray(fr, dtype=np.uint8))
            if len(final_sequence) >= target_total_frames:
                break

    os.makedirs(os.path.dirname(os.path.abspath(output_mp4_path)), exist_ok=True)

    import imageio.v2 as imageio
    temp_mp4 = output_mp4_path + ".tmp.mp4" if (audio_path and os.path.isfile(audio_path)) else output_mp4_path

    writer = imageio.get_writer(
        temp_mp4,
        format="FFMPEG",
        mode="I",
        fps=fps,
        codec="libx264",
        pixelformat="yuv420p",
        quality=8,
        ffmpeg_params=["-movflags", "+faststart"],
    )
    for arr in final_sequence:
        writer.append_data(arr)
    writer.close()

    # 如果传入了自定义音频轨道，则混流进 MP4
    if audio_path and os.path.isfile(audio_path):
        ffmpeg_exe = _get_ffmpeg_exe()
        if ffmpeg_exe:
            cmd = [
                ffmpeg_exe,
                "-y",
                "-i", temp_mp4,
                "-i", audio_path,
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "128k",
                "-shortest",
                "-movflags", "+faststart",
                output_mp4_path,
            ]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            if os.path.isfile(temp_mp4) and os.path.isfile(output_mp4_path):
                try:
                    os.remove(temp_mp4)
                except OSError:
                    pass
        else:
            shutil.move(temp_mp4, output_mp4_path)

    return output_mp4_path


def process_video_for_livephoto(
    video_path: str,
    output_mp4_path: str,
    start_time: float = 0.0,
    end_time: Optional[float] = 2.0,
    preserve_audio: bool = True,
) -> str:
    """
    处理本地或 SDK 生成的视频以用于实况照片合成（对齐并增强 W4J1e/Video2LivePhoto）：
    - 当未做裁剪（start_time <= 0.05 且 end_time is None）且已启用保留原声时，
      直接无损复制原始视频字节流，100% 保留原始画质、HEVC/H.264 编码与原视频声音！
    - 当指定了裁剪区间或需移除音轨时，调用内置 FFmpeg 精准截取并封装为 faststart MP4。
    """
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"未找到视频文件: {video_path}")

    os.makedirs(os.path.dirname(os.path.abspath(output_mp4_path)), exist_ok=True)
    is_trimmed = (start_time and start_time > 0.05) or (end_time is not None and end_time > 0)

    if not is_trimmed and preserve_audio:
        if os.path.abspath(video_path) != os.path.abspath(output_mp4_path):
            shutil.copyfile(video_path, output_mp4_path)
        return output_mp4_path

    ffmpeg_exe = _get_ffmpeg_exe()
    if not ffmpeg_exe:
        # 降级：直接复制原视频
        if os.path.abspath(video_path) != os.path.abspath(output_mp4_path):
            shutil.copyfile(video_path, output_mp4_path)
        return output_mp4_path

    cmd = [ffmpeg_exe, "-y"]
    if start_time and start_time > 0:
        cmd += ["-ss", f"{start_time:.3f}"]
    cmd += ["-i", video_path]
    if end_time is not None and end_time > start_time:
        duration = end_time - start_time
        cmd += ["-t", f"{duration:.3f}"]

    cmd += [
        "-vf", "scale='min(1920,iw)':'min(1920,ih)':force_original_aspect_ratio=decrease,scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-c:v", "libx264",
        "-profile:v", "high",
        "-level:v", "4.2",
        "-preset", "fast",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
    ]
    if preserve_audio:
        cmd += ["-c:a", "aac", "-b:a", "128k"]
    else:
        cmd += ["-an"]

    cmd += ["-movflags", "+faststart", output_mp4_path]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if res.returncode != 0 or not os.path.isfile(output_mp4_path):
        if os.path.abspath(video_path) != os.path.abspath(output_mp4_path):
            shutil.copyfile(video_path, output_mp4_path)
    return output_mp4_path


def extract_cover_from_video(
    video_path: str,
    output_jpg_path: str,
    timestamp_sec: float = 0.0,
    quality: int = 95,
) -> str:
    """从视频指定时间点提取高清实况封面图 (.jpg)"""
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"未找到视频文件: {video_path}")

    os.makedirs(os.path.dirname(os.path.abspath(output_jpg_path)), exist_ok=True)
    ffmpeg_exe = _get_ffmpeg_exe()

    if ffmpeg_exe:
        cmd = [
            ffmpeg_exe,
            "-y",
            "-ss", f"{max(0.0, timestamp_sec):.3f}",
            "-i", video_path,
            "-frames:v", "1",
            "-q:v", "2",
            output_jpg_path,
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if os.path.isfile(output_jpg_path) and os.path.getsize(output_jpg_path) > 0:
            return output_jpg_path

    # 降级使用 imageio 读取首帧
    import imageio.v3 as iio
    for frame_arr in iio.imiter(video_path):
        im = Image.fromarray(frame_arr).convert("RGB")
        im.save(output_jpg_path, format="JPEG", quality=quality)
        return output_jpg_path

    raise RuntimeError(f"无法从视频提取封面帧: {video_path}")
