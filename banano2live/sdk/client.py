# -*- coding: utf-8 -*-
"""
HrioAPI 官方多模态 SDK 内置封装模块 (banano2live)
零外部框架依赖，原生支持 https://hrioapi.hrio.site 平台：
  1. 视频生成大模型 (/v1/videos + 异步任务轮询 /v1/videos/{task_id} + 动态 Contract 解析)
     - 支持文生视频 (Text-to-Video)
     - 支持图生视频 / 首尾帧生视频 (Image-to-Video / First-Last Frame)
     - 支持视频转绘 (Video-to-Video)
     - 原生支持保留生成音轨 (generate_audio=True)
  2. 图像生成大模型 (/v1/images/generations)
     - 支持 3x3 九宫格 / 4x4 十六宫格连续微动序列帧生图
     - 支持文生图、参考图生图（垫图锁脸）、双图动作迁移、4K 超高清 (4096x4096)
  3. 媒体预签名上传 (/api/uploads/presign) 与模型目录查询 (/v1/key/models)
"""

import os
import time
import json
import base64
import mimetypes
import urllib.request
import urllib.parse
import urllib.error
from typing import Optional, Dict, Any, Tuple, List, Callable

DEFAULT_BASE_URL = "https://hrioapi.hrio.site/v1"
OFFICIAL_WEBSITE = "https://hrioapi.hrio.site"
DEFAULT_IMAGE_MODEL = "gemini-nano-banana-2.1"
DEFAULT_VIDEO_MODEL = "veo-3.0-fast-generate-001"


class HrioAPIError(Exception):
    """HrioAPI 平台请求异常"""
    pass


def file_to_data_uri(file_path: str) -> str:
    """将本地媒体文件编码为 Data URI (base64)"""
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"未找到本地文件: {file_path}")

    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        ext = os.path.splitext(file_path)[1].lower()
        if ext in (".jpg", ".jpeg"):
            mime_type = "image/jpeg"
        elif ext == ".webp":
            mime_type = "image/webp"
        elif ext == ".gif":
            mime_type = "image/gif"
        elif ext in (".mp4", ".m4v"):
            mime_type = "video/mp4"
        elif ext == ".mov":
            mime_type = "video/quicktime"
        else:
            mime_type = "image/png"

    with open(file_path, "rb") as f:
        data = f.read()
    b64 = base64.b64encode(data).decode("utf-8")
    return f"data:{mime_type};base64,{b64}"


def _extract_nested(data: Any, path: str) -> Any:
    """支持点号与数组下标路径提取，如 'output[0].url' 或 'response.generatedVideos[0].video.uri'"""
    cur = data
    for segment in path.split("."):
        if cur is None:
            return None
        if "[" in segment and segment.endswith("]"):
            key, idx_str = segment[:-1].split("[", 1)
            if key:
                if not isinstance(cur, dict):
                    return None
                cur = cur.get(key)
            if not isinstance(cur, list):
                return None
            try:
                idx = int(idx_str)
            except ValueError:
                return None
            if idx < 0 or idx >= len(cur):
                return None
            cur = cur[idx]
        else:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(segment)
    return cur


class HrioClient:
    """
    轻量自包含 HrioAPI 多模态客户端（支持图像宫格生成 + 视频生成 + 异步任务轮询）。
    支持传入 api_key，若未传则自动读取环境变量 HRIO_API_KEY 或当前目录 .env。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 300,
        poll_interval: float = 3.0,
        poll_timeout: int = 600,
    ):
        resolved_key = (api_key or os.environ.get("HRIO_API_KEY", "")).strip()
        if not resolved_key:
            resolved_key = self._load_key_from_dotenv()
        self.api_key = resolved_key
        raw_base = (base_url or os.environ.get("HRIO_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        if not raw_base.endswith("/v1"):
            self.root_url = raw_base
            self.base_url = f"{raw_base}/v1"
        else:
            self.base_url = raw_base
            self.root_url = raw_base[:-3]
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout

    @staticmethod
    def _load_key_from_dotenv() -> str:
        for candidate in (".env", os.path.join("..", ".env")):
            if os.path.isfile(candidate):
                try:
                    with open(candidate, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("HRIO_API_KEY="):
                                return line.split("=", 1)[1].strip().strip('"').strip("'")
                except Exception:
                    pass
        return ""

    def check_auth(self):
        if not self.api_key:
            raise HrioAPIError(
                f"\n[错误] 未检测到有效的 API Key！\n"
                f"请前往官方网站注册并获取您的 API Key: {OFFICIAL_WEBSITE}\n"
                f"使用方式：\n"
                f"  1. 环境变量配置：export HRIO_API_KEY=\"sk-xxxx\" 或 $env:HRIO_API_KEY=\"sk-xxxx\"\n"
                f"  2. 代码传参配置：client = HrioClient(api_key=\"sk-xxxx\")\n"
                f"  3. 命令行参数：python main.py --key \"sk-xxxx\"\n"
            )

    def _request_json(
        self,
        method: str,
        url: str,
        payload: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        self.check_auth()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "banano2live-sdk/1.0",
            "Accept": "application/json",
        }
        data_bytes = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data_bytes = json.dumps(payload).encode("utf-8")
        if extra_headers:
            headers.update(extra_headers)

        req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                resp_text = resp.read().decode("utf-8", errors="replace")
                return json.loads(resp_text) if resp_text.strip() else {}
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            raise HrioAPIError(
                f"HTTP 请求失败 ({e.code}) [{url}]: {err_body}\n"
                f"请检查 Key 余额或前往官网管理：{OFFICIAL_WEBSITE}"
            ) from e
        except Exception as e:
            raise HrioAPIError(f"请求失败 [{url}]: {e}") from e

    def list_models(self, model_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取平台支持的模型目录（可按 'video' / 'image' 过滤）"""
        url = f"{self.base_url}/key/models"
        resp = self._request_json("GET", url, timeout=30)
        models = resp.get("data", []) if isinstance(resp, dict) else []
        if model_type:
            models = [m for m in models if str(m.get("model_type", "")).lower() == model_type.lower()]
        return models

    def get_contract(self, model: str) -> Dict[str, Any]:
        """获取指定模型的动态调用契约 (/v1/key/models/{model}/contract)"""
        encoded = urllib.parse.quote(model.strip(), safe="")
        url = f"{self.base_url}/key/models/{encoded}/contract"
        return self._request_json("GET", url, timeout=30)

    def upload_media(self, file_path: str, kind: str = "image") -> str:
        """
        尝试通过 /api/uploads/presign 预签名上传本地图片/视频获取公网稳定 HTTPS URL；
        若预签名接口不可用则自动降级为 Base64 Data URI。
        """
        if file_path.startswith(("http://", "https://", "data:")):
            return file_path
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"未找到本地媒体文件: {file_path}")

        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = "image/jpeg" if file_path.lower().endswith((".jpg", ".jpeg")) else "image/png"

        with open(file_path, "rb") as f:
            raw_bytes = f.read()

        directory = {
            "image": "workspace/images",
            "video": "workspace/videos",
            "audio": "workspace/audio",
        }.get(kind.lower(), "workspace/assets")

        try:
            presign_url = f"{self.root_url}/api/uploads/presign"
            presign = self._request_json(
                "POST",
                presign_url,
                payload={
                    "filename": os.path.basename(file_path),
                    "content_type": mime_type,
                    "file_size": len(raw_bytes),
                    "qiniu_dir": directory,
                    "dir": directory,
                },
                extra_headers={
                    "x-api-key": self.api_key,
                    "x-goog-api-key": self.api_key,
                },
                timeout=20,
            )
            upload_url = (
                presign.get("upload_url")
                or presign.get("uploadUrl")
                or presign.get("presigned_url")
                or presign.get("put_url")
                or presign.get("url")
            )
            public_url = (
                presign.get("public_url")
                or presign.get("publicUrl")
                or presign.get("file_url")
                or presign.get("fileUrl")
                or presign.get("read_url")
            )
            method = str(presign.get("method") or "PUT").upper()
            if upload_url and method == "PUT":
                put_req = urllib.request.Request(
                    upload_url,
                    data=raw_bytes,
                    headers={"Content-Type": mime_type},
                    method="PUT",
                )
                with urllib.request.urlopen(put_req, timeout=60) as _:
                    pass
                if public_url and str(public_url).startswith("https://"):
                    return str(public_url)
        except Exception:
            pass

        return file_to_data_uri(file_path)

    # =========================================================================
    # 1. 图像生成接口（支持 3x3 / 4x4 宫格序列帧生成、参考图锁脸、动作迁移、4K）
    # =========================================================================
    def generate_image(
        self,
        model: str,
        prompt: str,
        images: Optional[List[str]] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """调用 /v1/images/generations 图像生成接口"""
        self.check_auth()
        url = f"{self.base_url}/images/generations"
        payload: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "size": "1024x1024",
        }

        if images:
            formatted_images: List[str] = []
            for img in images:
                img_str = str(img).strip()
                if img_str.startswith(("http://", "https://", "data:")):
                    formatted_images.append(img_str)
                elif os.path.isfile(img_str):
                    formatted_images.append(file_to_data_uri(img_str))
                else:
                    formatted_images.append(img_str)
            payload["images"] = formatted_images
            payload["media"] = [{"kind": "image", "url": u} for u in formatted_images]

        if parameters:
            payload.update(parameters)

        return self._request_json("POST", url, payload=payload)

    def extract_image_bytes_or_url(self, resp_data: Dict[str, Any]) -> Tuple[Optional[str], Optional[bytes]]:
        """从响应体中解析图片 URL 或 Base64 图片二进制"""
        if not isinstance(resp_data, dict):
            return None, None

        items = resp_data.get("data")
        if isinstance(items, list) and items:
            first = items[0]
            if isinstance(first, dict):
                if first.get("b64_json"):
                    return None, base64.b64decode(first["b64_json"])
                if first.get("url"):
                    return first["url"], None

        images_list = resp_data.get("images")
        if isinstance(images_list, list) and images_list:
            first = images_list[0]
            if isinstance(first, dict) and first.get("url"):
                return first["url"], None
            if isinstance(first, str):
                return first, None

        for k in ("url", "image_url", "output_url"):
            val = resp_data.get(k)
            if isinstance(val, str) and val.startswith(("http://", "https://")):
                return val, None

        return None, None

    # =========================================================================
    # 2. 视频生成接口（支持文生视频、图生视频、首尾帧生视频、自动轮询异步任务）
    # =========================================================================
    def generate_video(
        self,
        model: str = DEFAULT_VIDEO_MODEL,
        prompt: str = "",
        images: Optional[List[str]] = None,
        video_url: Optional[str] = None,
        aspect_ratio: str = "9:16",
        duration: int = 5,
        resolution: str = "1K",
        generate_audio: bool = True,
        async_mode: bool = True,
        wait: bool = True,
        on_progress: Optional[Callable[[str, Optional[float], Dict[str, Any]], None]] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        调用 /v1/videos 视频生成接口。
        支持：
          - 文生视频 (Text-to-Video): 仅传 prompt
          - 图生视频 (Image-to-Video): 传 images=[first_frame]
          - 首尾帧生视频 (First-Last Frame): 传 images=[first_frame, last_frame]
          - 视频生视频 (Video-to-Video): 传 video_url
        当返回异步任务 ID 时，自动轮询 /v1/videos/{task_id} 直至获取最终视频 URL。
        """
        self.check_auth()
        url = f"{self.base_url}/videos"

        m_lower = model.strip().lower()
        if m_lower in ("omni", "gemini-omni"):
            model = "gemini-omni-flash-preview"
            m_lower = model
        eff_duration = int(duration)
        eff_res = resolution
        eff_ar = aspect_ratio

        # 针对各视频大模型上游契约自动规范化参数，防止 400 参数报错
        if "gemini-omni" in m_lower:
            if eff_ar not in ("16:9", "9:16"):
                eff_ar = "16:9"
            if video_url:
                eff_res = "720p"
            elif eff_res not in ("720p", "1080p", "4K", "1K"):
                eff_res = "1K"
        elif "veo-" in m_lower:
            # veo-3.0 / veo-3.1 上游仅支持 duration=8
            eff_duration = 8
            if eff_ar not in ("16:9", "9:16"):
                eff_ar = "9:16"
            if "veo-3.1" in m_lower:
                if eff_res not in ("720p", "1080p", "4K"):
                    eff_res = "720p"
            else:
                eff_res = None
        elif "seedance" in m_lower:
            eff_duration = max(4, min(15, eff_duration if eff_duration != 5 else 6))
            eff_res = "720p"
            if "doubao-seedance-2-0" in m_lower:
                eff_ar = "16:9"
        elif "sora" in m_lower or "grok-imagine-video" in m_lower:
            eff_duration = 8
            eff_res = None
        elif "minimax" in m_lower:
            eff_duration = max(4, min(15, eff_duration))
            if eff_res not in ("720p", "768P", "1K", "2K"):
                eff_res = "720p"

        payload: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "aspect_ratio": eff_ar,
            "duration": eff_duration,
            "async": bool(async_mode),
        }
        if "seedance" not in m_lower:
            payload["seconds"] = eff_duration
            payload["generate_audio"] = bool(generate_audio)
        if eff_res:
            payload["resolution"] = eff_res

        if images:
            resolved_imgs: List[str] = []
            for img in images:
                img_str = str(img).strip()
                if img_str.startswith(("http://", "https://", "data:")):
                    resolved_imgs.append(img_str)
                elif os.path.isfile(img_str):
                    resolved_imgs.append(self.upload_media(img_str, kind="image"))
                else:
                    resolved_imgs.append(img_str)

            if resolved_imgs:
                payload["image"] = resolved_imgs[0]
                payload["image_url"] = resolved_imgs[0]
                payload["images"] = resolved_imgs
                payload["image_urls"] = resolved_imgs
                if not video_url and "gemini-omni" not in m_lower:
                    payload["first_image_url"] = resolved_imgs[0]
                if len(resolved_imgs) >= 2:
                    payload["extra_images"] = resolved_imgs[1:]
                    payload["Ingredients_images"] = resolved_imgs
                    payload["ingredients_images"] = resolved_imgs
                    if not video_url and "gemini-omni" not in m_lower:
                        payload["last_image_url"] = resolved_imgs[1]

        if video_url:
            if os.path.isfile(video_url):
                payload["video_url"] = self.upload_media(video_url, kind="video")
            else:
                payload["video_url"] = video_url

        if parameters:
            payload.update(parameters)

        if on_progress:
            on_progress("submitted", 0.0, payload)

        initial_resp = self._request_json("POST", url, payload=payload)

        # 检查是否直接返回了视频 URL
        direct_url = self.extract_video_url(initial_resp)
        if direct_url:
            if on_progress:
                on_progress("completed", 100.0, initial_resp)
            return {
                "ok": True,
                "model": model,
                "video_url": direct_url,
                "response": initial_resp,
            }

        # 提取异步任务 ID 进行轮询
        task_id = self.extract_task_id(initial_resp)
        if not task_id:
            raise HrioAPIError(f"视频生成响应中既无直接视频链接也无任务 ID: {initial_resp}")

        if not wait:
            return {
                "ok": True,
                "model": model,
                "task_id": task_id,
                "video_url": None,
                "response": initial_resp,
            }

        final_resp = self.poll_video_task(task_id=task_id, model=model, on_progress=on_progress)
        video_out_url = self.extract_video_url(final_resp)
        if not video_out_url:
            # 尝试访问 /v1/videos/{task_id}/content
            content_url = f"{self.base_url}/videos/{urllib.parse.quote(str(task_id), safe='')}/content"
            video_out_url = content_url

        return {
            "ok": True,
            "model": model,
            "task_id": task_id,
            "video_url": video_out_url,
            "response": final_resp,
        }

    def poll_video_task(
        self,
        task_id: str,
        model: Optional[str] = None,
        on_progress: Optional[Callable[[str, Optional[float], Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """轮询异步视频生成任务状态 (/v1/videos/{task_id})"""
        self.check_auth()
        encoded_id = urllib.parse.quote(str(task_id).strip(), safe="")
        status_url = f"{self.base_url}/videos/{encoded_id}"

        pending_states = {"queued", "pending", "submitted", "processing", "running", "in_progress", ""}
        success_states = {"completed", "succeeded", "success", "done", "finished"}
        failure_states = {"failed", "error", "canceled", "cancelled", "expired", "rejected", "timeout"}

        deadline = time.time() + self.poll_timeout
        while time.time() < deadline:
            resp = self._request_json("GET", status_url, timeout=60)
            state_raw = (
                resp.get("status")
                or resp.get("state")
                or resp.get("task_status")
                or _extract_nested(resp, "data.status")
                or ""
            )
            if isinstance(state_raw, bool):
                state = "done" if state_raw else "pending"
            else:
                state = str(state_raw).strip().lower()

            progress = None
            for pf in ("progress", "progress_percent", "data.progress"):
                pv = _extract_nested(resp, pf)
                if isinstance(pv, (int, float)):
                    progress = float(pv) * 100.0 if float(pv) <= 1.0 and float(pv) > 0 else float(pv)
                    break
                elif isinstance(pv, str) and pv.endswith("%"):
                    try:
                        progress = float(pv[:-1])
                        break
                    except ValueError:
                        pass

            if on_progress:
                on_progress(state or "processing", progress, resp)

            vid_url = self.extract_video_url(resp)
            if state in success_states or vid_url:
                if on_progress:
                    on_progress("completed", 100.0, resp)
                return resp

            if state in failure_states:
                err_msg = (
                    resp.get("error")
                    or resp.get("message")
                    or _extract_nested(resp, "error.message")
                    or resp
                )
                raise HrioAPIError(f"视频生成任务失败 (task_id={task_id}, state={state}): {err_msg}")

            if state not in pending_states and vid_url:
                return resp

            time.sleep(self.poll_interval)

        raise HrioAPIError(f"视频生成任务轮询超时 (task_id={task_id}, 超过 {self.poll_timeout}s)")

    @staticmethod
    def extract_task_id(resp_data: Dict[str, Any]) -> Optional[str]:
        """从响应体中提取异步任务 ID"""
        if not isinstance(resp_data, dict):
            return None
        for path in ("task_id", "id", "data.task_id", "data.id", "name", "operation_name"):
            val = _extract_nested(resp_data, path)
            if isinstance(val, str) and val.strip():
                return val.strip()
        return None

    @staticmethod
    def extract_video_url(resp_data: Dict[str, Any]) -> Optional[str]:
        """从响应体中提取生成的视频 URL"""
        if not isinstance(resp_data, dict):
            return None
        candidate_paths = (
            "video_url",
            "url",
            "output_url",
            "output[0].url",
            "result.video_url",
            "result.url",
            "data[0].url",
            "data.video_url",
            "data.url",
            "response.generatedVideos[0].video.uri",
            "response.generateVideoResponse.generatedSamples[0].video.uri",
        )
        for path in candidate_paths:
            val = _extract_nested(resp_data, path)
            if isinstance(val, str) and val.strip().startswith(("http://", "https://")):
                return val.strip()
        # 如果 output 直接是字符串 URL
        if isinstance(resp_data.get("output"), str) and resp_data["output"].startswith(("http://", "https://")):
            return resp_data["output"]
        return None

    def download_file(self, url: str, save_path: str) -> str:
        """下载远程图片或视频文件到本地路径"""
        os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
        headers = {"User-Agent": "Mozilla/5.0 (banano2live/1.0)"}
        if url.startswith(self.root_url) and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp, open(save_path, "wb") as out:
            out.write(resp.read())
        return save_path
