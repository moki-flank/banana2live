# -*- coding: utf-8 -*-
"""
banano2live 命令行工具 (CLI)
全面支持：
  1. AI 视频直生转实况图 (--mode video): 调用 Veo / Seedance / Sora-2 等视频模型生成带原声实况照片
  2. AI 宫格生图切分转实况图 (--mode grid): 调用 Nano Banana 2.1 等图像模型生成 3x3/4x4 宫格切分转实况照片
  3. 动作迁移宫格转实况图 (--motion-source + --image)
  4. 本地视频 + 自定义封面离线转实况图 (--video [--cover])，保留原视频声音
  5. 本地 3x3 / 4x4 宫格大图离线切分转实况图 (--from-grid)
  6. 实况照片字节级逆向验真与拆解 (--inspect)
"""

import os
import sys
import json
import base64
import argparse
import webbrowser
import urllib.error
import urllib.request
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def _inline_generated_images(resp_obj: dict) -> dict:
    """Download remote image URLs in /images/generations response on backend to prevent browser Canvas CORS tainting."""
    if not isinstance(resp_obj, dict):
        return resp_obj
    items = resp_obj.get("data")
    if not isinstance(items, list):
        return resp_obj
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("b64_json") and not item.get("data_url"):
            item["data_url"] = f"data:image/png;base64,{item['b64_json']}"
            continue
        img_url = item.get("url")
        if isinstance(img_url, str) and img_url.startswith(("http://", "https://")) and not item.get("b64_json"):
            try:
                req = urllib.request.Request(
                    img_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) banano2live-proxy/1.1",
                        "Referer": "https://hrioapi.hrio.site/",
                    },
                )
                with urllib.request.urlopen(req, timeout=120) as r:
                    raw = r.read()
                    ctype = (r.headers.get("Content-Type") or "image/png").split(";")[0].strip()
                b64_str = base64.b64encode(raw).decode("ascii")
                item["b64_json"] = b64_str
                item["data_url"] = f"data:{ctype};base64,{b64_str}"
            except Exception:
                pass
    return resp_obj


class Banano2LiveRequestHandler(SimpleHTTPRequestHandler):
    """内置支持 HrioAPI 反向代理 (/api/v1/*, /v1/*)、跨域媒体代理 (/api/proxy?url=...) 与私有网络访问 (PNA) 的本地静态与桥接服务"""

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def _is_hrio_api_path(self) -> bool:
        p = self.path.split("?", 1)[0]
        return p.startswith("/api/v1/") or p.startswith("/v1/")

    def _handle_hrio_api_proxy(self, method: str):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        clean_path = parsed.path
        if clean_path.startswith("/api/v1/"):
            subpath = clean_path[len("/api/v1/"):]
        elif clean_path.startswith("/v1/"):
            subpath = clean_path[len("/v1/"):]
        else:
            subpath = clean_path.lstrip("/")

        target_base = (
            self.headers.get("X-Target-Base-Url")
            or (qs.get("target_base") or [""])[0]
            or os.environ.get("HRIO_BASE_URL")
            or "https://hrioapi.hrio.site/v1"
        ).strip().rstrip("/")

        forward_qs = {k: v for k, v in qs.items() if k not in ("target_base", "api_key")}
        query_str = urllib.parse.urlencode(forward_qs, doseq=True)
        target_url = f"{target_base}/{subpath}"
        if query_str:
            target_url = f"{target_url}?{query_str}"

        auth_header = (self.headers.get("Authorization") or "").strip()
        if not auth_header or auth_header.lower() == "bearer":
            q_key = (qs.get("api_key") or [""])[0].strip()
            env_key = os.environ.get("HRIO_API_KEY", "").strip()
            use_key = q_key or env_key
            if use_key:
                auth_header = use_key if use_key.lower().startswith("bearer ") else f"Bearer {use_key}"

        length = int(self.headers.get("Content-Length", "0") or "0")
        body_bytes = self.rfile.read(length) if length > 0 else None

        req_headers = {
            "User-Agent": "banano2live-proxy/1.1",
            "Accept": "application/json, */*",
        }
        if self.headers.get("Content-Type"):
            req_headers["Content-Type"] = self.headers.get("Content-Type")
        elif body_bytes is not None:
            req_headers["Content-Type"] = "application/json"
        if auth_header:
            req_headers["Authorization"] = auth_header

        req = urllib.request.Request(
            target_url,
            data=body_bytes,
            headers=req_headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                resp_bytes = resp.read()
                status_code = resp.status
                ctype = resp.headers.get("Content-Type", "application/json; charset=utf-8")
        except urllib.error.HTTPError as e:
            resp_bytes = e.read()
            status_code = e.code
            ctype = e.headers.get("Content-Type", "application/json; charset=utf-8") if e.headers else "application/json; charset=utf-8"
        except Exception as e:
            err_payload = json.dumps({"error": {"message": f"本地代理请求上游失败: {e}"}}, ensure_ascii=False).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(err_payload)))
            self.end_headers()
            self.wfile.write(err_payload)
            return

        if status_code == 200 and "images/generations" in subpath:
            try:
                resp_obj = json.loads(resp_bytes.decode("utf-8"))
                resp_obj = _inline_generated_images(resp_obj)
                resp_bytes = json.dumps(resp_obj, ensure_ascii=False).encode("utf-8")
                ctype = "application/json; charset=utf-8"
            except Exception:
                pass

        self.send_response(status_code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(resp_bytes)))
        self.end_headers()
        self.wfile.write(resp_bytes)

    def do_POST(self):
        if self._is_hrio_api_path():
            self._handle_hrio_api_proxy("POST")
            return
        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        if self._is_hrio_api_path():
            self._handle_hrio_api_proxy("GET")
            return

        if self.path.startswith("/api/ping"):
            env_key = os.environ.get("HRIO_API_KEY", "").strip()
            body = json.dumps({
                "ok": True,
                "service": "banano2live-proxy",
                "has_env_key": bool(env_key),
                "default_key": env_key,
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path.startswith("/api/proxy_js") or self.path.startswith("/api/proxy"):
            is_js = self.path.startswith("/api/proxy_js")
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            target_url = (qs.get("url") or [""])[0].strip()
            req_id = (qs.get("id") or ["cb"])[0].strip()
            dur_str = (qs.get("duration") or [""])[0].strip()
            trim_dur = float(dur_str) if dur_str and float(dur_str) > 0 else None

            if not target_url.startswith(("http://", "https://")):
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Invalid target url")
                return

            import base64 as _b64
            import tempfile
            from .cutter.video_synthesizer import process_video_for_livephoto

            try:
                req = urllib.request.Request(
                    target_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) banano2live/1.0",
                        "Referer": "https://hrioapi.hrio.site/",
                    },
                )
                with urllib.request.urlopen(req, timeout=120) as resp:
                    data = resp.read()
                    ctype = resp.headers.get("Content-Type", "application/octet-stream")

                if trim_dur and trim_dur > 0 and ("video" in ctype.lower() or target_url.lower().endswith((".mp4", ".mov", ".webm"))):
                    with tempfile.TemporaryDirectory() as tmpdir:
                        raw_p = os.path.join(tmpdir, "raw.mp4")
                        out_p = os.path.join(tmpdir, "trimmed.mp4")
                        with open(raw_p, "wb") as f:
                            f.write(data)
                        process_video_for_livephoto(raw_p, out_p, start_time=0.0, end_time=trim_dur, preserve_audio=True)
                        if os.path.isfile(out_p) and os.path.getsize(out_p) > 0:
                            with open(out_p, "rb") as f:
                                data = f.read()
                            ctype = "video/mp4"

                if is_js:
                    b64_str = _b64.b64encode(data).decode("ascii")
                    payload_obj = json.dumps({"ok": True, "mime": ctype, "b64": b64_str})
                    payload_js = (
                        f"(window.__B2L_PROXY_RESOLVE || window.__B2G_PROXY_RESOLVE) && "
                        f"(window.__B2L_PROXY_RESOLVE || window.__B2G_PROXY_RESOLVE)({json.dumps(req_id)}, {payload_obj});"
                    ).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/javascript; charset=utf-8")
                    self.send_header("Content-Length", str(len(payload_js)))
                    self.end_headers()
                    self.wfile.write(payload_js)
                else:
                    self.send_response(200)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
            except Exception as e:
                if is_js:
                    err_obj = json.dumps({"ok": False, "error": str(e)})
                    payload_js = (
                        f"(window.__B2L_PROXY_RESOLVE || window.__B2G_PROXY_RESOLVE) && "
                        f"(window.__B2L_PROXY_RESOLVE || window.__B2G_PROXY_RESOLVE)({json.dumps(req_id)}, {err_obj});"
                    ).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/javascript; charset=utf-8")
                    self.send_header("Content-Length", str(len(payload_js)))
                    self.end_headers()
                    self.wfile.write(payload_js)
                else:
                    err_bytes = json.dumps({"ok": False, "error": str(e)}).encode("utf-8")
                    self.send_response(502)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(err_bytes)))
                    self.end_headers()
                    self.wfile.write(err_bytes)
            return

        if self.path in ("/", "/index.html"):
            self.path = "/web/index.html"
        return super().do_GET()

from .core import Banano2Live, DEFAULT_IMAGE_MODEL, DEFAULT_VIDEO_MODEL
from .prompts.engine import ACTION_PRESETS, LIVE_VIDEO_PRESETS
from .sdk.client import OFFICIAL_WEBSITE
from .cutter.livephoto_builder import inspect_motion_photo


def _print_bundle_summary(title: str, res: dict):
    print("\n" + "=" * 62)
    print(f"🎉 {title}")
    print("-" * 62)
    if res.get("mode"):
        print(f"🧭 运行模式:       {res['mode']}")
    if res.get("model"):
        print(f"🤖 调用模型:       {res['model']}")
    if res.get("grid"):
        print(f"📐 宫格规格:       {res['grid']} (共 {res.get('total_frames', 9)} 帧)")
    if res.get("grid_image"):
        print(f"🖼️ 宫格原图:       {res['grid_image']}")
    if res.get("cover_jpg"):
        print(f"📸 静态封面图:     {res['cover_jpg']}")
    if res.get("video_mp4"):
        print(f"🎞️ 实况视频流:     {res['video_mp4']}")
    if res.get("motion_photo_jpg"):
        print(f"📱 Google 实况图:  {res['motion_photo_jpg']} (单文件 .jpg，支持小米/安卓/Win11/群晖)")
    if res.get("apple_live_zip"):
        print(f"🍎 Apple 实况包:   {res['apple_live_zip']} (配对 .JPG + .MOV 归档)")
    if res.get("gif_path"):
        print(f"✨ 附属预览 GIF:   {res['gif_path']}")
    if res.get("webp_path"):
        print(f"🌐 附属预览 WebP:  {res['webp_path']}")
    ver = res.get("verification")
    if isinstance(ver, dict):
        status = "✅ 通过 (XMP + MP4 ftyp 签名完好)" if ver.get("valid") else "⚠️ 未通过"
        print(f"🔍 实况二进制验真: {status} | 总大小: {ver.get('total_bytes', 0):,} B (封面 {ver.get('cover_bytes', 0):,} B + 视频 {ver.get('video_bytes', 0):,} B)")
    print("=" * 62 + "\n")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        prog="banano2live",
        description=f"🍌 banano2live - 全模态 AI 视频/宫格图转实况照片 (Live Photo) 引擎 | 官网: {OFFICIAL_WEBSITE}",
    )
    parser.add_argument("prompt", nargs="?", default=None, help="实况照片画面与微动作描述提示词")
    parser.add_argument(
        "--mode",
        choices=["grid", "video"],
        default="grid",
        help="AI 生成模式：grid=宫格生图切分转实况 (默认)，video=SDK视频直生转实况 (支持原声)",
    )
    parser.add_argument("--image", "-i", default=None, help="参考图路径/URL（图生实况、首帧图或动作迁移目标角色图）")
    parser.add_argument("--last-image", default=None, help="视频生成模式的尾帧参考图路径/URL（首尾帧过渡生实况）")
    parser.add_argument("--cover", "-c", default=None, help="自定义实况照片静态封面图路径 (.jpg/.png)")
    parser.add_argument("--video", "-v", default=None, help="本地视频文件路径（离线将 MP4/MOV/WebM 转为实况照片，保留原声）")
    parser.add_argument("--from-grid", default=None, help="本地已有的 3x3 或 4x4 宫格大图路径（离线切分合成实况照片）")
    parser.add_argument("--motion-source", "-m", default=None, help="动作源媒体路径 (.gif/.webp/.mp4)，将动作迁移到 --image 角色并生成实况图")
    parser.add_argument("--preset", "-p", default=None, help="内置微动作预设名称 (使用 --list-presets 查看)")
    parser.add_argument("--grid", "-g", choices=["3x3", "4x4"], default="3x3", help="宫格切分规格：3x3 (9帧) 或 4x4 (16帧超丝滑)")
    parser.add_argument("--4k", dest="is_4k", action="store_true", help="开启 4K 超高清 (4096x4096) 宫格出图")
    parser.add_argument("--transparent", "-t", action="store_true", help="开启外边缘 BFS 智能去底，并合成至 --backdrop 实况背景色")
    parser.add_argument("--backdrop", default="#FFFFFF", help="宫格去底后的实况背景色 (默认 #FFFFFF 纯白)")
    parser.add_argument("--loop-mode", choices=["pingpong", "loop"], default="pingpong", help="宫格帧合成视频循环方式：pingpong (往返无缝) 或 loop (正序循环)")
    parser.add_argument("--fps", type=int, default=16, help="宫格合成实况视频的基础帧率 (默认 16 FPS，配合插值达 32 FPS)")
    parser.add_argument("--crossfade", type=int, default=1, help="相邻宫格帧之间的平滑过渡插值帧数 (默认 1)")
    parser.add_argument("--cover-index", type=int, default=0, help="宫格模式下选作实况封面的帧序号 (从 0 开始，默认第 0 帧)")
    parser.add_argument("--export-size", type=int, default=None, help="宫格切分后单帧导出像素尺寸 (如 640, 1080)")
    parser.add_argument("--audio", default=None, help="为宫格实况混入的外部音频文件路径 (.mp3/.wav/.aac)")
    parser.add_argument("--aspect-ratio", default="9:16", help="SDK 视频生成宽高比 (默认 9:16 竖屏实况，可选 16:9, 1:1)")
    parser.add_argument("--duration", type=int, default=5, help="SDK 视频生成时长秒数 (默认 5 秒)")
    parser.add_argument("--start-time", type=float, default=0.0, help="本地视频裁剪起始时间（秒，默认 0）")
    parser.add_argument("--end-time", type=float, default=2.0, help="实况视频截取结束时间（秒，默认 2.0 秒黄金实况时长，传 0 则保留全长）")
    parser.add_argument("--cover-time", type=float, default=0.0, help="从视频提取封面的时间点（秒，默认 0.0 首帧）")
    parser.add_argument("--mute", action="store_true", help="禁用视频声音（默认保留原视频声音）")
    parser.add_argument("--format", "-f", choices=["both", "google", "apple"], default="both", help="导出实况格式：both (默认双格式)、google (单文件 .jpg)、apple (.zip)")
    parser.add_argument("--key", "-k", default=None, help="HrioAPI 平台 API Key (也可设置环境变量 HRIO_API_KEY)")
    parser.add_argument("--base-url", default=None, help="自定义 API Base URL")
    parser.add_argument("--image-model", default=DEFAULT_IMAGE_MODEL, help=f"宫格生图模型 (默认: {DEFAULT_IMAGE_MODEL})")
    parser.add_argument("--video-model", default=DEFAULT_VIDEO_MODEL, help=f"视频直生模型 (默认: {DEFAULT_VIDEO_MODEL})")
    parser.add_argument("--out", "-o", default="output", help="产物输出目录 (默认 output/)")
    parser.add_argument("--name", "-n", default="livephoto", help="导出文件基础名称 (默认 livephoto)")
    parser.add_argument("--inspect", default=None, help="逆向验真并拆解指定的实况照片 (.jpg) 文件")
    parser.add_argument("--list-presets", action="store_true", help="列出所有内置实况图微动作与视频预设")
    parser.add_argument("--serve", type=int, nargs="?", const=8095, default=None, help="启动本地静态 Web 服务打开纯前端工作台 (默认端口 8095)")
    parser.add_argument("--no-browser", action="store_true", help="启动 --serve 时不自动弹出浏览器窗口")

    args = parser.parse_args()

    if args.list_presets:
        print("\n=== 🎬 1. SDK 视频直生实况图预设 (LIVE_VIDEO_PRESETS) ===")
        for k, v in LIVE_VIDEO_PRESETS.items():
            print(f"  * {k:16s} - {v['title']} ({v['description']})")
        print("\n=== 🧩 2. SDK 宫格切分实况图预设 (ACTION_PRESETS) ===")
        for k, v in ACTION_PRESETS.items():
            print(f"  * {k:16s} - {v['title']} ({v['description']})")
        print()
        return

    if args.inspect:
        extract_dir = os.path.join(args.out, "inspected_" + os.path.splitext(os.path.basename(args.inspect))[0])
        info = inspect_motion_photo(args.inspect, extract_dir=extract_dir)
        print("\n=== 🔍 实况照片 (Motion Photo) 二进制验真报告 ===")
        print(json.dumps(info, indent=2, ensure_ascii=False))
        return

    if args.serve is not None:
        port = args.serve
        web_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        os.chdir(web_root)
        url = f"http://127.0.0.1:{port}/web/index.html"
        print(f"🚀 banano2live Web 实况图工作台与跨域媒体代理已启动: {url}")
        if not args.no_browser:
            try:
                webbrowser.open(url)
            except Exception:
                pass
        server = ThreadedHTTPServer(("127.0.0.1", port), Banano2LiveRequestHandler)
        server.serve_forever()
        return

    app = Banano2Live(
        api_key=args.key,
        base_url=args.base_url,
        image_model=args.image_model,
        video_model=args.video_model,
    )

    try:
        # 1. 本地视频离线转实况图
        if args.video:
            res = app.local_video_to_live(
                video_path=args.video,
                custom_cover_path=args.cover or args.image,
                start_time=args.start_time,
                end_time=args.end_time,
                cover_timestamp=args.cover_time,
                preserve_audio=not args.mute,
                output_dir=args.out,
                base_name=args.name,
                fmt=args.format,
            )
            _print_bundle_summary("本地视频转实况照片成功！", res)
            return

        # 2. 本地宫格大图离线切分转实况图
        if args.from_grid:
            res = app.local_grid_to_live(
                grid_image_path=args.from_grid,
                custom_cover_path=args.cover,
                grid=args.grid,
                output_dir=args.out,
                base_name=args.name,
                fps=args.fps,
                loop_mode=args.loop_mode,
                crossfade_steps=args.crossfade,
                cover_frame_index=args.cover_index,
                transparent=args.transparent,
                backdrop=args.backdrop,
                export_size=args.export_size,
                audio_path=args.audio,
                fmt=args.format,
            )
            _print_bundle_summary("本地宫格大图切分转实况照片成功！", res)
            return

        # 3. 动作迁移宫格转实况图
        if args.motion_source and args.image:
            res = app.transfer_motion_to_live(
                source_media=args.motion_source,
                target_image=args.image,
                action_hint=args.prompt or "transfer the exact motion and poses from the motion guide to the target character",
                grid=args.grid,
                output_dir=args.out,
                base_name=args.name,
                fps=args.fps,
                loop_mode=args.loop_mode,
                crossfade_steps=args.crossfade,
                transparent=args.transparent,
                backdrop=args.backdrop,
                is_4k=args.is_4k,
                export_size=args.export_size,
                fmt=args.format,
            )
            _print_bundle_summary("动作迁移实况照片生成成功！", res)
            return

        # 4. SDK 视频直生转实况图
        if args.mode == "video" or args.last_image:
            res = app.video_gen_to_live(
                prompt=args.prompt or "soft breeze blowing hair, natural eye blink and warm smile",
                image_path=args.image,
                last_image_path=args.last_image,
                custom_cover_path=args.cover,
                preset=args.preset,
                aspect_ratio=args.aspect_ratio,
                duration=args.duration,
                generate_audio=not args.mute,
                cover_timestamp=args.cover_time,
                output_dir=args.out,
                base_name=args.name,
                fmt=args.format,
            )
            _print_bundle_summary("SDK 视频直生转实况照片成功！", res)
            return

        if not args.prompt and not args.preset and not args.image:
            parser.print_help()
            print(f"\n💡 提示：可传入提示词、--image 参考图、--video 本地视频或 --from-grid 本地宫格图。\n🔑 官方 API Key 获取地址: {OFFICIAL_WEBSITE}\n")
            sys.exit(1)

        # 5. SDK 宫格生图切分转实况图
        res = app.grid_gen_to_live(
            prompt=args.prompt or "gently waving and smiling happily",
            image_path=args.image,
            custom_cover_path=args.cover,
            preset=args.preset,
            grid=args.grid,
            output_dir=args.out,
            base_name=args.name,
            fps=args.fps,
            loop_mode=args.loop_mode,
            crossfade_steps=args.crossfade,
            cover_frame_index=args.cover_index,
            transparent=args.transparent,
            backdrop=args.backdrop,
            is_4k=args.is_4k,
            export_size=args.export_size,
            audio_path=args.audio,
            fmt=args.format,
        )
        _print_bundle_summary("SDK 宫格生图切分转实况照片成功！", res)

    except Exception as e:
        print(f"\n[错误] {e}\n", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

