# banano2live 🍌➡️📸

> **全能 AI 视频 / 宫格图 / 本地媒体转实况照片 (Live Photo / Motion Photo) 引擎**  
> 原生支持【**纯 Web 前端零安装开箱即用 (Pure Web SPA · 本地浏览器处理 · 隐私安全)**】！  
> 原生支持【**SDK 视频直生转实况 (`/v1/videos`)**】与【**SDK 3×3 / 4×4 宫格生图切分转实况 (`/v1/images/generations`)**】双引擎！  
> 原生支持【**Google Motion Photo 单文件 (`.jpg`)**】与【**Apple Live Photo 配对包 (`.zip` 含同名 `.JPG` + `.MOV`)**】双规范导出！  
> 深度借鉴并全面增强 [**W4J1e/Video2LivePhoto**](https://github.com/W4J1e/Video2LivePhoto) 与 **banano2gif**，完整保留原视频声音，内置 iOS 同款同心圆 `LIVE` 按住播放交互舞台与二进制逆向验真解包器！

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8%2B-brightgreen.svg)](https://www.python.org/)
[![Web App](https://img.shields.io/badge/Web%20App-Zero%20Install%20Pure%20JS-amber.svg)](web/index.html)
[![Live Photo](https://img.shields.io/badge/Format-Google%20Motion%20Photo%20%2B%20Apple%20MOV-10b981.svg)](#)
[![API Platform](https://img.shields.io/badge/API%20Platform-HrioAPI-orange.svg)](https://hrioapi.hrio.site)

---

## 🌟 效果展示 (Demo Showcase)

| 1. AI 渲染 3×3 / 4×4 宫格原图 | 2. 自适应切帧 + 平滑插值动态效果 | 3. 封装单文件实况照片 (`sample_3x3_live.jpg`) |
| :---: | :---: | :---: |
| <img src="examples/sample_grid_3x3.jpg" width="280" alt="3x3 宫格原图" /> | <img src="examples/sample_3x3.gif" width="240" alt="切帧合成动态效果" /> | <img src="examples/sample_3x3_cover.jpg" width="240" alt="实况照片封面 (下载 sample_3x3_live.jpg 可在手机相册长按播放)" /> |

> 💡 **实况文件直接体验**：`examples/sample_3x3_live.jpg`、`examples/sample_4x4_live.jpg` 与带原声的 `examples/sample_audio_3x3_live.jpg` 已注入完整的 **Google Motion Photo v1/v2 XMP 元数据与 H.264 MP4 视频流**，可直接发送至安卓手机（小米 HyperOS/MIUI、OPPO、vivo、三星、Google 相册）、Windows 11 照片应用或群晖（Synology Photos），或者直接拖入本项目网页端的「🔍 实况验真/解包」标签页按住播放！

---

## 🌐 纯网页端零安装方案 (Pure Web SPA · 开箱即用)

借鉴并深度升级 [**W4J1e/Video2LivePhoto**](https://github.com/W4J1e/Video2LivePhoto)，本项目提供**100% 纯静态前端网页应用 (`web/index.html`)**：

* **零安装、免配环境**：直接双击 `web/index.html`（或根目录 `index.html`）即可在 Chrome / Edge / Safari 浏览器中直接运行，**甚至无需启动本地 HTTP 服务器（兼容 `file://` 协议双击直开）**；
* **本地浏览器内处理，隐私安全**：本地视频剪辑、封面抽帧、宫格自适应切分、BFS 边缘抠图、XMP 二进制段注入与 ZIP 归档全部在浏览器本地内存完成，绝不上传第三方服务器；
* **免 Key 一键体验 Demo**：网页右上角提供 **「⚡ 免 Key 一键生成实况示例」** 按钮，零配置 2 秒内即可在右侧 **iOS 风格 `LIVE` 交互舞台**体验“按住画面放大并播放实况与声音”的完整效果；
* **完美保留原视频声音**：
  * **未剪辑视频直通模式**：直接复用原始视频二进制流（保留原始 H.264 / HEVC 编码与原始 AAC 音轨，零画质损耗）；
  * **时间轴剪辑模式**：通过滑块截取精彩片段，自动通过 `captureStream()` 克隆原视频音轨并重混输出。

---

## 🚀 五大核心工作流模式 (SDK 双擎 + 离线双模 + 逆向验真)

### 1. 🎬 SDK 视频直生转实况图 (`--mode video` / `/v1/videos`)
内置封装 **HrioAPI** 视频生成 SDK（支持 `veo-3.0-fast-generate-001`、`veo-3.1-fast-generate-preview`、`doubao-seedance-2-0-pro-fast`、`seedance-2.5`、`sora-2`、`grok-imagine-video` 等主流视频大模型）：
* **文生视频转实况 (Text-to-Video Live Photo)**：输入提示词或选用内置实况预设（🍃 微风拂发、✨ 回眸一笑、☕ 咖啡热气、🌧️ 霓虹雨夜等），AI 直接生成带环境原声的短视频并封装为实况照片；
* **图生视频转实况 (Image-to-Video Live Photo)**：上传一张高清人像/插画/宠物照片，**直接将该原图作为实况照片的静态高画质封面**，同时以该图作为首帧驱动 AI 生成 3~5 秒自然微动视频流——相册静止时 100% 保持原图画质，长按瞬间鲜活灵动！
* **首尾帧过渡转实况 (First-Last Frame Live Photo)**：同时传入首帧图 `--image` 与尾帧图 `--last-image`，生成丝滑过渡的实况照片。

```bash
# 文生带原声视频并直接导出为实况照片 (.jpg + .zip)
python main.py "阳光下的少女微风吹拂发丝，自然眨眼微笑" --mode video --preset breeze_portrait

# 图生视频转实况（原图直接作为高清静态封面 + AI 生成动态与环境音）
python main.py "微风轻轻吹动头发，温柔眨眼微笑" --mode video --image "portrait.jpg"
```

### 2. 🧩 SDK 宫格生图切分转实况图 (`--mode grid` / `/v1/images/generations`)
继承并升级 `banano2gif` 的宫格序列帧引擎（默认接入 `gemini-nano-banana-2.1`、`gpt-image-2`、`gemini-3.1-flash-image`）：
* **支持 `3×3` 九宫格 (9帧) 与 `4×4` 十六宫格 (16帧超丝滑)**，以及 **`--4k` 超高清 (`4096×4096 UHD`)**；
* **自适应安全区切帧 + 外边缘 BFS 智能去底 (`--transparent`) + 实况底色合成 (`--backdrop`)**；
* **乒乓往返循环 (`pingpong`) + 帧间平滑插值 (`--crossfade`)**：自动将 9/16 帧插值扩展并编码为 2.4 秒高码率 H.264 MP4 视频流，彻底解决普通动图帧数少、无法被手机相册识别为实况图的痛点；
* **支持参考图锁脸 (`--image`) 与双图动作迁移 (`--motion-source`)**！

```bash
# 1. 文生 3x3 宫格切分转实况图（开启 BFS 去底并合成暖米色实况背景）
python main.py "可爱的3D柴犬戴着红色围巾开心挥手" --mode grid --preset waving --transparent --backdrop "#FFF8F0"

# 2. 4x4 十六宫格 + 4K 超清图生实况（参考图锁脸）
python main.py "俏皮眨眼比心" --mode grid --image "avatar.png" --preset wink --grid 4x4 --4k

# 3. 动作迁移转实况：将现有 GIF/MP4 的动作迁移至新角色并导出实况照片
python main.py --image "my_character.png" --motion-source "dance.gif" --grid 4x4 --transparent
```

### 3. 🎥 本地视频 + 自定义封面离线转实况图 (`--video`)
无需任何 API Key，直接将从抖音、微博、小红书保存的短视频或本地素材转换为手机相册原生识别的实况照片，并保留原视频声音：
```bash
# 将本地视频直接无损转为实况照片（保留原视频编码与原声）
python main.py --video "clip.mp4"

# 截取视频 0.5s ~ 3.2s 片段，并指定自定义高清图片作为实况静态封面
python main.py --video "clip.mp4" --cover "custom_cover.jpg" --start-time 0.5 --end-time 3.2
```

### 4. 🖼️ 本地宫格大图离线切分转实况图 (`--from-grid`)
```bash
# 将本地已有的 3x3 或 4x4 宫格大图切分并合成为实况照片（同时导出 .gif 与 .webp）
python main.py --from-grid "examples/sample_grid_3x3.jpg" --grid 3x3 --transparent --backdrop "#FFF8F0"
```

### 5. 🔍 实况照片字节级逆向验真与无损解包 (`--inspect`)
对任意生成的 Google Motion Photo `.jpg` 执行二进制结构校验，自动验证 `APP1 (0xFFE1)` XMP 字段与尾部 `ftyp` MP4 容器签名，并无损分离还原出 `extracted_cover.jpg` 与 `extracted_video.mp4`：
```bash
python main.py --inspect "examples/sample_3x3_live.jpg"
```

---

## 🔬 实况照片双格式底层规范说明

| 导出格式 | 产物形态 | 技术原理 | 完美兼容平台 |
| :--- | :--- | :--- | :--- |
| **Google Motion Photo** | 单文件 `*_live.jpg` | 在 JPEG `0xFFE1 (APP1)` 段同时注入 **MotionPhoto v1** (`GCamera:MotionPhoto="1"`, `GCamera:MicroVideoOffset`, `GCamera:MotionPhotoVideoOffset`) 与 **MotionPhoto v2** (`Container:Directory`) 双规范 XMP 元数据，并在 JPEG `EOI (0xFFD9)` 尾部无损拼接 MP4 视频流 | 安卓全系相册（小米 HyperOS/MIUI、OPPO/一加、vivo、华为/荣耀、三星、Pixel）、Google Photos、**Windows 10/11 照片应用**、**群晖 Synology Photos** |
| **Apple Live Photo** | 归档包 `*_apple_live.zip` | 内含同名配对的高清封面 `*.JPG`、实况视频流 `*.MOV` 以及包含 `contentIdentifier` UUID 的 `livephoto_manifest.json` | iOS / macOS 相册导入、Windows 照片应用、群晖 Synology Photos |

---

## 🔑 获取与配置 HrioAPI Key

当使用 AI 视频生成或 AI 宫格生图模式时，本项目通过内置零依赖 SDK 直连 **HrioAPI** 官方平台：
1. 前往官方网站注册并获取 API Key：👉 **[https://hrioapi.hrio.site](https://hrioapi.hrio.site)**
2. 配置环境变量或通过 `--key` 传入：
   ```bash
   # Windows PowerShell
   $env:HRIO_API_KEY="sk-xxxxxxxxxxxxxxxx"

   # Linux / macOS
   export HRIO_API_KEY="sk-xxxxxxxxxxxxxxxx"
   ```

---

## 📦 Python SDK 代码调用示例

```python
from banano2live import Banano2Live, banano2live, inspect_motion_photo

# 1. 初始化引擎
app = Banano2Live(api_key="sk-xxxxxxxx")

# 2. SDK 视频直生转实况图（支持文生视频 / 图生视频 / 首尾帧，保留原声）
res_video = app.video_gen_to_live(
    prompt="微风吹拂发丝，温柔回眸一笑",
    image_path="portrait.jpg",       # 可选：既是视频首帧，又直接作为高清实况封面
    preset="turn_smile",
    aspect_ratio="9:16",
    duration=5,
    generate_audio=True,
    output_dir="output",
    base_name="my_portrait_live",
)
print("Google 实况照片 (.jpg):", res_video["motion_photo_jpg"])
print("Apple 实况压缩包 (.zip):", res_video["apple_live_zip"])

# 3. SDK 3x3 / 4x4 宫格生图切分转实况图
res_grid = app.grid_gen_to_live(
    prompt="可爱的3D小熊挥手打招呼",
    preset="waving",
    grid="4x4",
    transparent=True,
    backdrop="#FFF8F0",
    is_4k=True,
    output_dir="output",
    base_name="bear_live",
)

# 4. 逆向验真并拆解生成的实况照片
report = inspect_motion_photo(res_grid["motion_photo_jpg"], extract_dir="output/unpacked")
print("验真结果:", report["valid"], "内嵌视频字节数:", report["video_bytes"])
```

---

## 📁 项目结构

```text
banano2live/
├── index.html                           # 根入口（自动跳转至 web/index.html）
├── main.py                              # CLI 命令行统一入口
├── requirements.txt                     # Python 依赖列表
├── setup.py                             # pip 包安装配置
├── banano2live.workbench-card.json      # Hrio Workbench Card v3 工作台配置卡
├── web/                                 # 纯网页端零安装实况图工作台 (借鉴并升级 W4J1e/Video2LivePhoto)
│   ├── index.html                       # 纯前端单页应用（支持双击直开或静态托管）
│   └── script/
│       ├── app.js                       # 前端主控交互与 iOS LIVE 播放器逻辑
│       ├── core/
│       │   ├── hrio-sdk.js              # 浏览器端 HrioAPI SDK（支持视频生成与宫格生图）
│       │   ├── video-processor.js       # 视频加载、裁剪抽帧、原声捕获与宫格帧转 MP4 编码器
│       │   ├── grid-slicer.js           # 纯前端 3x3/4x4 宫格切分、BFS 抠图与动作网格提取器
│       │   └── livephoto-builder.js     # Google Motion Photo (.jpg) XMP 注入、Apple (.zip) 打包与逆向验真器
│       └── utils/
│           ├── file-validator.js        # 媒体文件格式与体积校验器
│           └── ui-helper.js             # 通知、日志与时间格式化工具
├── banano2live/                         # Python 核心包
│   ├── __init__.py
│   ├── cli.py                           # 全功能命令行工具
│   ├── core.py                          # Banano2Live 多模态调度核心
│   ├── sdk/
│   │   └── client.py                    # HrioAPI 图像/视频生成与异步轮询原生客户端
│   ├── prompts/
│   │   └── engine.py                    # 视频实况 + 宫格切分双模态提示词引擎
│   └── cutter/
│       ├── slicer.py                    # 3x3 / 4x4 自适应中心切帧器
│       ├── matting.py                   # 外边缘 BFS 智能去底与实况背景合成
│       ├── motion_extractor.py          # 动作迁移序列帧采样与网格拼合
│       ├── video_synthesizer.py         # 序列帧插值合成 H.264 MP4 与视频无损裁剪
│       └── livephoto_builder.py         # 实况照片双格式构建与字节级逆向验真解包
└── examples/                            # 预置实测宫格图、切帧动图与真实可播放的实况照片样例
```

---

## 🤝 致谢与参考

* [**W4J1e/Video2LivePhoto**](https://github.com/W4J1e/Video2LivePhoto) — 纯静态网页端视频/图片合成实况照片与 XMP 注入方案参考
* **banano2gif** — 3×3 / 4×4 宫格连续微动作生成、自适应切分与外边缘 BFS 抠图流水线
* **[HrioAPI](https://hrioapi.hrio.site)** — 多模态视频生成（Veo / Seedance / Sora）与图像生成（Nano Banana / GPT-Image）SDK 平台支持