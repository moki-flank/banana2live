# -*- coding: utf-8 -*-
"""
banano2live 核心全模态实况图生成引擎
全面支持：
  1. 【SDK 视频直生转实况图 (AI Video-to-LivePhoto)】：
     支持文生视频、图生视频（垫图定格封面+动态延续）、首尾帧生视频，保留原视频声音，一键打包 Google Motion Photo (.jpg) 与 Apple Live Photo (.zip)。
  2. 【SDK 宫格生图切分转实况图 (AI Grid 3x3 / 4x4 Slicing-to-LivePhoto)】：
     支持文生宫格、图生宫格（锁脸）、动作迁移宫格（Motion Transfer）、4K 超清 (4096x4096)，
     自适应切分 9/16 帧 + BFS 去底 + 乒乓插值合成 H.264 MP4 + 实况照片双格式封装。
  3. 【本地视频/宫格大图零安装离线转实况图 (Local Video / Grid to LivePhoto)】：
     对齐并增强 W4J1e/Video2LivePhoto，支持时间轴裁剪、自定义静态封面、无损保留原声、实况图二进制逆向验真解包。
"""

import os
from typing import Optional, Dict, Any, List
from PIL import Image

from .sdk.client import (
    HrioClient,
    DEFAULT_BASE_URL,
    OFFICIAL_WEBSITE,
    DEFAULT_IMAGE_MODEL,
    DEFAULT_VIDEO_MODEL,
)
from .prompts.engine import (
    ACTION_PRESETS,
    LIVE_VIDEO_PRESETS,
    build_grid_live_prompt,
    build_video_live_prompt,
    build_motion_transfer_prompt,
)
from .cutter.slicer import slice_grid
from .cutter.motion_extractor import create_motion_guide_grid
from .cutter.video_synthesizer import (
    frames_to_mp4,
    process_video_for_livephoto,
    extract_cover_from_video,
    build_gif_or_webp,
)
from .cutter.livephoto_builder import (
    build_livephoto_bundle,
    inspect_motion_photo,
)


class Banano2Live:
    """
    banano2live 全模态 AI 实况图 (Live Photo / Motion Photo) 生成引擎
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        image_model: str = DEFAULT_IMAGE_MODEL,
        video_model: str = DEFAULT_VIDEO_MODEL,
    ):
        self.client = HrioClient(api_key=api_key, base_url=base_url)
        self.image_model = image_model
        self.video_model = video_model

    # =========================================================================
    # 通道 A：SDK 视频直生转实况图 (Video Generation -> Live Photo)
    # =========================================================================
    def video_gen_to_live(
        self,
        prompt: str,
        image_path: Optional[str] = None,
        last_image_path: Optional[str] = None,
        custom_cover_path: Optional[str] = None,
        preset: Optional[str] = None,
        style: str = "Cinematic live photo, ultra-high definition, natural lighting, shallow depth of field, authentic texture",
        aspect_ratio: str = "9:16",
        duration: int = 5,
        resolution: str = "1K",
        generate_audio: bool = True,
        use_ref_as_cover: bool = True,
        cover_timestamp: float = 0.0,
        live_duration: Optional[float] = 2.0,
        output_dir: str = "output",
        base_name: str = "video_gen_live",
        fmt: str = "both",
    ) -> Dict[str, Any]:
        """
        调用 HrioAPI 视频生成大模型（如 veo-3.0-fast-generate-001 / seedance / sora-2）
        直接生成带原声的高清短视频，并自动提取封面（或采用参考图/自定义封面）合成为实况照片。
        """
        os.makedirs(output_dir, exist_ok=True)
        images_input: List[str] = []
        if image_path:
            if not os.path.isfile(image_path) and not image_path.startswith(("http://", "https://", "data:")):
                raise FileNotFoundError(f"未找到参考首帧图片: {image_path}")
            images_input.append(image_path)
        if last_image_path:
            if not os.path.isfile(last_image_path) and not last_image_path.startswith(("http://", "https://", "data:")):
                raise FileNotFoundError(f"未找到参考尾帧图片: {last_image_path}")
            images_input.append(last_image_path)

        full_prompt = build_video_live_prompt(
            subject_and_action=prompt,
            preset=preset,
            style=style,
            has_reference_image=bool(image_path),
            has_last_frame=bool(last_image_path),
        )

        print(f"[banano2live] 🎬 模式: SDK 视频直生转实况 | 模型: {self.video_model} | 比例: {aspect_ratio} | 时长: {duration}s")
        def _progress(state: str, pct: Optional[float], _raw: Dict[str, Any]):
            pct_str = f" ({pct:.0f}%)" if pct is not None else ""
            print(f"[banano2live] ⏳ 视频生成状态: {state}{pct_str}")

        gen_res = self.client.generate_video(
            model=self.video_model,
            prompt=full_prompt,
            images=images_input if images_input else None,
            aspect_ratio=aspect_ratio,
            duration=duration,
            resolution=resolution,
            generate_audio=generate_audio,
            async_mode=True,
            wait=True,
            on_progress=_progress,
        )

        video_url = gen_res.get("video_url")
        if not video_url:
            raise RuntimeError(f"未能获取生成的视频 URL: {gen_res}")

        raw_video_path = os.path.join(output_dir, f"{base_name}_raw.mp4")
        print(f"[banano2live] ⬇️ 正在下载生成的视频流: {video_url} ...")
        self.client.download_file(video_url, raw_video_path)

        # 若设置了实况图目标时长（默认 2.0s），将长视频裁剪为 2.0s 实况黄金时长并保留原声
        if live_duration and live_duration > 0:
            trimmed_video_path = os.path.join(output_dir, f"{base_name}_2s.mp4")
            print(f"[banano2live] ✂️ 正在将实况视频流裁剪为默认 {live_duration:.1f}s (保留原声)...")
            live_video_source = process_video_for_livephoto(
                video_path=raw_video_path,
                output_mp4_path=trimmed_video_path,
                start_time=0.0,
                end_time=float(live_duration),
                preserve_audio=generate_audio,
            )
        else:
            live_video_source = raw_video_path

        # 确定实况照片封面：优先 custom_cover_path -> 其次首帧参考图 (若开启 use_ref_as_cover) -> 否则从视频抽帧
        if custom_cover_path and os.path.isfile(custom_cover_path):
            cover_src = custom_cover_path
        elif use_ref_as_cover and image_path and os.path.isfile(image_path):
            cover_src = image_path
        else:
            extracted_cover = os.path.join(output_dir, f"{base_name}_extracted_cover.jpg")
            cover_src = extract_cover_from_video(live_video_source, extracted_cover, timestamp_sec=cover_timestamp)

        print("[banano2live] 📦 正在封装 Google Motion Photo (.jpg) 与 Apple Live Photo (.zip)...")
        bundle = build_livephoto_bundle(
            cover_source=cover_src,
            video_source=live_video_source,
            output_dir=output_dir,
            base_name=base_name,
            fmt=fmt,
        )
        bundle.update({
            "mode": "video_gen_to_live",
            "model": self.video_model,
            "prompt": full_prompt,
            "video_url": video_url,
            "raw_video_path": raw_video_path,
            "official_website": OFFICIAL_WEBSITE,
        })
        return bundle

    # =========================================================================
    # 通道 B：SDK 宫格生图切分转实况图 (3x3 / 4x4 Grid Image -> Live Photo)
    # =========================================================================
    def grid_gen_to_live(
        self,
        prompt: str,
        image_path: Optional[str] = None,
        custom_cover_path: Optional[str] = None,
        preset: Optional[str] = None,
        grid: str = "3x3",
        style: str = "High-end 3D animation render, soft ambient lighting, clean solid white background, Pop Mart collectible figurine style",
        output_dir: str = "output",
        base_name: str = "grid_live",
        fps: int = 16,
        min_duration_sec: float = 3.0,
        loop_mode: str = "pingpong",
        crossfade_steps: int = 1,
        cover_frame_index: int = 0,
        transparent: bool = False,
        backdrop: str = "#FFFFFF",
        is_4k: bool = False,
        export_size: Optional[int] = None,
        audio_path: Optional[str] = None,
        fmt: str = "both",
    ) -> Dict[str, Any]:
        """
        调用 HrioAPI 图像生成大模型（如 gemini-nano-banana-2.1）生成 3x3 (9帧) 或 4x4 (16帧) 宫格图，
        自动精准切帧、可选去底、插值合成为平滑 H.264 MP4 视频流，并打包导出为实况照片 (.jpg / .zip)。
        """
        os.makedirs(output_dir, exist_ok=True)
        images_list: Optional[List[str]] = None
        if image_path:
            if not os.path.isfile(image_path) and not image_path.startswith(("http://", "https://", "data:")):
                raise FileNotFoundError(f"未找到参考图片: {image_path}")
            images_list = [image_path]

        full_prompt = build_grid_live_prompt(
            subject_and_action=prompt,
            preset=preset,
            grid=grid,
            style=style,
            has_reference_image=bool(images_list),
            is_4k=is_4k,
        )

        is_16 = "4" in str(grid) or str(grid) == "16"
        grid_label = "4x4 (16帧)" if is_16 else "3x3 (9帧)"
        req_size = "4096x4096" if is_4k else "1024x1024"

        print(f"[banano2live] 🧩 模式: SDK 宫格切分转实况 | 网格: {grid_label} | 分辨率: {req_size} | 模型: {self.image_model}")
        resp = self.client.generate_image(
            model=self.image_model,
            prompt=full_prompt,
            images=images_list,
            parameters={"size": req_size},
        )
        img_url, img_bytes = self.client.extract_image_bytes_or_url(resp)

        grid_save_path = os.path.join(output_dir, f"{base_name}_grid.jpg")
        if img_bytes:
            with open(grid_save_path, "wb") as f:
                f.write(img_bytes)
        elif img_url:
            self.client.download_file(img_url, grid_save_path)
        else:
            raise RuntimeError(f"未能从模型返回中提取有效宫格图数据: {resp}")

        res = self.local_grid_to_live(
            grid_image_path=grid_save_path,
            custom_cover_path=custom_cover_path,
            grid=grid,
            output_dir=output_dir,
            base_name=base_name,
            fps=fps,
            min_duration_sec=min_duration_sec,
            loop_mode=loop_mode,
            crossfade_steps=crossfade_steps,
            cover_frame_index=cover_frame_index,
            transparent=transparent,
            backdrop=backdrop,
            export_size=export_size,
            audio_path=audio_path,
            fmt=fmt,
        )
        res["mode"] = "image_grid_to_live" if image_path else "text_grid_to_live"
        res["prompt"] = full_prompt
        res["is_4k"] = is_4k
        res["model"] = self.image_model
        return res

    # =========================================================================
    # 通道 C：SDK 动作迁移宫格转实况图 (Motion Transfer -> Live Photo)
    # =========================================================================
    def transfer_motion_to_live(
        self,
        source_media: str,
        target_image: str,
        action_hint: str = "transfer the exact motion and poses from the motion guide to the target character",
        grid: str = "3x3",
        style: str = "Preserve target character art style, high quality render, clean solid white background",
        output_dir: str = "output",
        base_name: str = "motion_transfer_live",
        fps: int = 16,
        min_duration_sec: float = 3.0,
        loop_mode: str = "pingpong",
        crossfade_steps: int = 1,
        transparent: bool = False,
        backdrop: str = "#FFFFFF",
        is_4k: bool = False,
        export_size: Optional[int] = None,
        fmt: str = "both",
    ) -> Dict[str, Any]:
        """从现有 GIF/WebP/视频 提取动作网格，迁移至目标角色图并合成为实况照片"""
        os.makedirs(output_dir, exist_ok=True)
        guide_path = os.path.join(output_dir, f"{base_name}_motion_guide.jpg")
        print(f"[banano2live] 🎭 1. 正在从源媒体提取动作参考网格 ({grid}): {source_media} ...")
        create_motion_guide_grid(source_media, guide_path, grid=grid)

        full_prompt = build_motion_transfer_prompt(
            action_hint=action_hint,
            grid=grid,
            style=style,
            is_4k=is_4k,
        )
        req_size = "4096x4096" if is_4k else "1024x1024"
        print(f"[banano2live] 🎭 2. 请求多模态双图动作迁移生图 (模型: {self.image_model}, 规格: {req_size})...")
        resp = self.client.generate_image(
            model=self.image_model,
            prompt=full_prompt,
            images=[target_image, guide_path],
            parameters={"size": req_size},
        )
        img_url, img_bytes = self.client.extract_image_bytes_or_url(resp)
        grid_save_path = os.path.join(output_dir, f"{base_name}_grid.jpg")
        if img_bytes:
            with open(grid_save_path, "wb") as f:
                f.write(img_bytes)
        elif img_url:
            self.client.download_file(img_url, grid_save_path)
        else:
            raise RuntimeError(f"未能从动作迁移响应中提取有效图片: {resp}")

        res = self.local_grid_to_live(
            grid_image_path=grid_save_path,
            grid=grid,
            output_dir=output_dir,
            base_name=base_name,
            fps=fps,
            min_duration_sec=min_duration_sec,
            loop_mode=loop_mode,
            crossfade_steps=crossfade_steps,
            transparent=transparent,
            backdrop=backdrop,
            export_size=export_size,
            fmt=fmt,
        )
        res.update({
            "mode": "motion_transfer_to_live",
            "source_media": source_media,
            "target_image": target_image,
            "motion_guide": guide_path,
            "prompt": full_prompt,
        })
        return res

    # =========================================================================
    # 通道 D：本地宫格大图离线切分转实况图 (Local 3x3 / 4x4 Grid -> Live Photo)
    # =========================================================================
    def local_grid_to_live(
        self,
        grid_image_path: str,
        custom_cover_path: Optional[str] = None,
        grid: str = "3x3",
        output_dir: str = "output",
        base_name: str = "grid_live",
        fps: int = 16,
        min_duration_sec: float = 3.0,
        loop_mode: str = "pingpong",
        crossfade_steps: int = 1,
        cover_frame_index: int = 0,
        transparent: bool = False,
        backdrop: str = "#FFFFFF",
        export_size: Optional[int] = None,
        audio_path: Optional[str] = None,
        fmt: str = "both",
    ) -> Dict[str, Any]:
        """将本地已有的 3x3 或 4x4 宫格大图离线切分并合成为实况照片（兼导出 GIF / WebP）"""
        if not os.path.isfile(grid_image_path):
            raise FileNotFoundError(f"未找到宫格图片文件: {grid_image_path}")

        os.makedirs(output_dir, exist_ok=True)
        frames_dir = os.path.join(output_dir, f"{base_name}_frames")
        is_16 = "4" in str(grid) or str(grid) == "16"

        print(f"[banano2live] ✂️ 正在切分宫格图 ({'4x4 16帧' if is_16 else '3x3 9帧'}, 去底: {transparent})...")
        frames = slice_grid(
            grid_image_path,
            output_dir=frames_dir,
            grid_layout=grid,
            export_size=export_size,
            transparent=transparent,
        )

        # 同时生成附属 GIF 与 WebP 动图方便跨平台预览
        dur_ms = 100 if is_16 else 160
        gif_path = os.path.join(output_dir, f"{base_name}.gif")
        webp_path = os.path.join(output_dir, f"{base_name}.webp")
        build_gif_or_webp(frames, gif_path, duration_ms=dur_ms)
        build_gif_or_webp(frames, webp_path, duration_ms=dur_ms)

        # 合成 H.264 MP4 实况视频流
        mp4_path = os.path.join(output_dir, f"{base_name}_stream.mp4")
        print(f"[banano2live] 🎞️ 正在合成 H.264 实况视频流 (fps={fps}, mode={loop_mode}, crossfade={crossfade_steps})...")
        frames_to_mp4(
            frames,
            output_mp4_path=mp4_path,
            fps=fps,
            min_duration_sec=min_duration_sec,
            loop_mode=loop_mode,
            crossfade_steps=crossfade_steps,
            backdrop=backdrop,
            audio_path=audio_path,
        )

        # 选择封面图
        if custom_cover_path and os.path.isfile(custom_cover_path):
            cover_src = custom_cover_path
        else:
            idx = max(0, min(len(frames) - 1, int(cover_frame_index)))
            cover_src = frames[idx]

        print("[banano2live] 📦 正在构建实况照片产物包 (Google Motion Photo .jpg + Apple Live Photo .zip)...")
        bundle = build_livephoto_bundle(
            cover_source=cover_src,
            video_source=mp4_path,
            output_dir=output_dir,
            base_name=base_name,
            fmt=fmt,
            backdrop=backdrop,
        )
        bundle.update({
            "mode": "local_grid_to_live",
            "grid": "4x4" if is_16 else "3x3",
            "grid_image": grid_image_path,
            "frames_dir": frames_dir,
            "total_frames": len(frames),
            "frame_resolution": (frames[0].width, frames[0].height),
            "gif_path": gif_path,
            "webp_path": webp_path,
            "official_website": OFFICIAL_WEBSITE,
        })
        return bundle

    # =========================================================================
    # 通道 E：本地视频 + 自定义封面离线转实况图 (Local Video -> Live Photo)
    # =========================================================================
    def local_video_to_live(
        self,
        video_path: str,
        custom_cover_path: Optional[str] = None,
        start_time: float = 0.0,
        end_time: Optional[float] = 2.0,
        cover_timestamp: float = 0.0,
        preserve_audio: bool = True,
        output_dir: str = "output",
        base_name: str = "video_live",
        fmt: str = "both",
    ) -> Dict[str, Any]:
        """
        将本地视频文件直接转换（或与自定义封面图合并）为实况照片，保留原视频声音。
        对齐并增强 W4J1e/Video2LivePhoto。
        """
        if not os.path.isfile(video_path):
            raise FileNotFoundError(f"未找到输入视频文件: {video_path}")

        os.makedirs(output_dir, exist_ok=True)
        processed_mp4 = os.path.join(output_dir, f"{base_name}_processed.mp4")

        print(f"[banano2live] 🎥 正在处理视频流 ({video_path}, 保留原声: {preserve_audio})...")
        process_video_for_livephoto(
            video_path=video_path,
            output_mp4_path=processed_mp4,
            start_time=start_time,
            end_time=end_time,
            preserve_audio=preserve_audio,
        )

        if custom_cover_path and os.path.isfile(custom_cover_path):
            cover_src = custom_cover_path
        else:
            extracted_jpg = os.path.join(output_dir, f"{base_name}_extracted_cover.jpg")
            cover_src = extract_cover_from_video(
                video_path=processed_mp4,
                output_jpg_path=extracted_jpg,
                timestamp_sec=cover_timestamp,
            )

        print("[banano2live] 📦 正在合成 Google Motion Photo (.jpg) 与 Apple Live Photo (.zip)...")
        bundle = build_livephoto_bundle(
            cover_source=cover_src,
            video_source=processed_mp4,
            output_dir=output_dir,
            base_name=base_name,
            fmt=fmt,
        )
        bundle.update({
            "mode": "local_video_to_live",
            "video_input": video_path,
            "preserve_audio": preserve_audio,
            "official_website": OFFICIAL_WEBSITE,
        })
        return bundle


def banano2live(
    prompt: Optional[str] = None,
    mode: str = "auto",
    image_path: Optional[str] = None,
    last_image_path: Optional[str] = None,
    video_path: Optional[str] = None,
    grid_image_path: Optional[str] = None,
    motion_source: Optional[str] = None,
    custom_cover_path: Optional[str] = None,
    preset: Optional[str] = None,
    grid: str = "3x3",
    aspect_ratio: str = "9:16",
    duration: int = 5,
    fps: int = 16,
    loop_mode: str = "pingpong",
    transparent: bool = False,
    backdrop: str = "#FFFFFF",
    is_4k: bool = False,
    export_size: Optional[int] = None,
    start_time: float = 0.0,
    end_time: Optional[float] = 2.0,
    preserve_audio: bool = True,
    fmt: str = "both",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    image_model: str = DEFAULT_IMAGE_MODEL,
    video_model: str = DEFAULT_VIDEO_MODEL,
    output_dir: str = "output",
    base_name: str = "livephoto",
) -> Dict[str, Any]:
    """
    banano2live 统一多模态智能入口：
      - 本地视频转实况 (传入 video_path)
      - 本地宫格图切分转实况 (传入 grid_image_path)
      - 动作迁移转实况 (传入 motion_source + image_path)
      - AI 视频直生转实况 (mode="video" 或传入 last_image_path)
      - AI 宫格生图切分转实况 (mode="grid" 或默认宫格切分模式)
    """
    app = Banano2Live(
        api_key=api_key,
        base_url=base_url,
        image_model=image_model,
        video_model=video_model,
    )

    if video_path:
        return app.local_video_to_live(
            video_path=video_path,
            custom_cover_path=custom_cover_path or image_path,
            start_time=start_time,
            end_time=end_time,
            preserve_audio=preserve_audio,
            output_dir=output_dir,
            base_name=base_name,
            fmt=fmt,
        )

    if grid_image_path:
        return app.local_grid_to_live(
            grid_image_path=grid_image_path,
            custom_cover_path=custom_cover_path,
            grid=grid,
            output_dir=output_dir,
            base_name=base_name,
            fps=fps,
            loop_mode=loop_mode,
            transparent=transparent,
            backdrop=backdrop,
            export_size=export_size,
            fmt=fmt,
        )

    if motion_source and image_path:
        return app.transfer_motion_to_live(
            source_media=motion_source,
            target_image=image_path,
            action_hint=prompt or "transfer the exact motion and poses from the motion guide to the target character",
            grid=grid,
            output_dir=output_dir,
            base_name=base_name,
            fps=fps,
            loop_mode=loop_mode,
            transparent=transparent,
            backdrop=backdrop,
            is_4k=is_4k,
            export_size=export_size,
            fmt=fmt,
        )

    if mode in ("video", "video_gen", "t2v", "i2v") or last_image_path:
        return app.video_gen_to_live(
            prompt=prompt or "gentle breeze blowing hair, natural eye blink and warm smile",
            image_path=image_path,
            last_image_path=last_image_path,
            custom_cover_path=custom_cover_path,
            preset=preset,
            aspect_ratio=aspect_ratio,
            duration=duration,
            generate_audio=preserve_audio,
            output_dir=output_dir,
            base_name=base_name,
            fmt=fmt,
        )

    return app.grid_gen_to_live(
        prompt=prompt or "A cute 3D character smiling warmly and waving gently",
        image_path=image_path,
        custom_cover_path=custom_cover_path,
        preset=preset,
        grid=grid,
        output_dir=output_dir,
        base_name=base_name,
        fps=fps,
        loop_mode=loop_mode,
        transparent=transparent,
        backdrop=backdrop,
        is_4k=is_4k,
        export_size=export_size,
        fmt=fmt,
    )
