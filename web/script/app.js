/**
 * banano2live - 纯网页端 AI 视频/宫格图/本地媒体转实况照片 (Live Photo) 主控脚本
 * 融合 W4J1e/Video2LivePhoto 与 banano2gif 的全部特性：
 *   - Tab 1 (video-sdk): AI 视频直生转实况 (SDK /v1/videos，内置模型契约自适应参数对齐 + 跨域无损代理拉取)
 *   - Tab 2 (grid-sdk):  AI 宫格切分转实况 (SDK /v1/images/generations，支持 3x3/4x4、参考图锁脸、动作迁移、4K)
 *   - Tab 3 (local-vid): 本地视频 + 自定义封面转实况 (零安装离线处理、时间轴剪辑、未剪辑原视频无损直通保留原声)
 *   - Tab 4 (local-grd): 本地 3x3/4x4 宫格大图离线切分转实况 (支持一键加载内置示例宫格体验)
 *   - Tab 5 (inspector): 实况照片 (.jpg) 字节级逆向验真与无损解包器
 */
(function () {
  const B2L = window.Banano2Live || {};
  const {
    FileValidator,
    showNotification,
    appendLog,
    formatTime,
    LivePhotoBuilder,
    VideoProcessor,
    sliceGridCanvas,
    createMotionGuideDataUrl,
    LIVE_VIDEO_PRESETS,
    ACTION_PRESETS,
    buildVideoLivePrompt,
    buildGridLivePrompt,
    buildMotionTransferPrompt,
    HrioWebClient,
  } = B2L;

  document.addEventListener('DOMContentLoaded', () => {
    const videoProcessor = new VideoProcessor();
    const livePhotoBuilder = new LivePhotoBuilder(videoProcessor);

    // 全局状态
    let activeTab = 'video-sdk';
    let selectedVideoPreset = 'breeze_portrait';
    let selectedGridPreset = 'breeze';
    let videoSdkFirstImgDataUrl = null;
    let videoSdkLastImgDataUrl = null;
    let gridSdkRefImgDataUrl = null;
    let gridSdkMotionFile = null;
    let localVideoFile = null;
    let localCoverBlob = null;
    let localVideoDuration = 0;

    let currentSlicedCanvases = [];
    let currentSlicedUrls = [];
    let selectedCoverFrameIdx = 0;
    let currentResultBundle = null;
    let isPlayingLive = false;

    // 0. 安全读取与持久化 API Key (捕获 file:// 下的 storage 限制，避免控制台报错)
    const apiKeyInput = document.getElementById('apiKeyInput');
    if (apiKeyInput) {
      try {
        const savedKey = window.localStorage && window.localStorage.getItem('BANANO2LIVE_API_KEY');
        if (savedKey && !apiKeyInput.value) apiKeyInput.value = savedKey;
      } catch (_e) {}
      apiKeyInput.addEventListener('input', () => {
        try {
          if (window.localStorage) {
            window.localStorage.setItem('BANANO2LIVE_API_KEY', apiKeyInput.value.trim());
          }
        } catch (_e) {}
      });
    }

    // 视频模型切换时自动匹配最优时长与画幅，防止上游 400 参数报错
    const videoModelSelect = document.getElementById('videoModelSelect');
    const videoDurationSelect = document.getElementById('videoDurationSelect');
    const videoAspectSelect = document.getElementById('videoAspectSelect');
    videoModelSelect?.addEventListener('change', () => {
      const m = (videoModelSelect.value || '').toLowerCase();
      if (m.includes('veo-') || m.includes('sora') || m.includes('grok')) {
        if (videoDurationSelect) videoDurationSelect.value = '8';
        if (m.includes('veo-3.1') && videoAspectSelect && videoAspectSelect.value === '1:1') {
          videoAspectSelect.value = '9:16';
        }
        appendLog('已切换模型 ' + videoModelSelect.value + '，已自动匹配标准时长 8 秒');
      } else if (m.includes('seedance')) {
        if (videoDurationSelect) videoDurationSelect.value = '6';
        if (m.includes('doubao-seedance-2-0') && videoAspectSelect) {
          videoAspectSelect.value = '16:9';
        }
        appendLog('已切换模型 ' + videoModelSelect.value + '，已自动匹配标准时长 6 秒 (720p)');
      }
    });

    // 1. 初始化预设胶囊
    const videoPresetsWrap = document.getElementById('videoPresetsWrap');
    if (videoPresetsWrap && LIVE_VIDEO_PRESETS) {
      Object.entries(LIVE_VIDEO_PRESETS).forEach(([key, val]) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'preset-pill' + (key === selectedVideoPreset ? ' active' : '');
        btn.textContent = val.title;
        btn.onclick = () => {
          selectedVideoPreset = key;
          videoPresetsWrap.querySelectorAll('.preset-pill').forEach((p) => p.classList.remove('active'));
          btn.classList.add('active');
          const inp = document.getElementById('videoSdkPrompt');
          if (inp && !inp.value.trim()) {
            inp.value = val.desc;
          }
        };
        videoPresetsWrap.appendChild(btn);
      });
    }

    const gridPresetsWrap = document.getElementById('gridPresetsWrap');
    if (gridPresetsWrap && ACTION_PRESETS) {
      Object.entries(ACTION_PRESETS).forEach(([key, val]) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'preset-pill' + (key === selectedGridPreset ? ' active' : '');
        btn.textContent = val.title;
        btn.onclick = () => {
          selectedGridPreset = key;
          gridPresetsWrap.querySelectorAll('.preset-pill').forEach((p) => p.classList.remove('active'));
          btn.classList.add('active');
        };
        gridPresetsWrap.appendChild(btn);
      });
    }

    // 2. Tab 切换
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabPanes = document.querySelectorAll('.tab-pane');
    tabBtns.forEach((btn) => {
      btn.addEventListener('click', () => {
        activeTab = btn.dataset.tab;
        tabBtns.forEach((b) => b.classList.remove('active'));
        tabPanes.forEach((p) => p.classList.remove('active'));
        btn.classList.add('active');
        const target = document.getElementById('pane-' + activeTab);
        if (target) target.classList.add('active');
      });
    });

    // 3. 工具：读取图片文件为 DataURL
    function bindImageUpload(zoneId, inputId, previewId, onLoaded) {
      const zone = document.getElementById(zoneId);
      const input = document.getElementById(inputId);
      const preview = document.getElementById(previewId);
      if (!zone || !input) return;

      zone.addEventListener('click', () => input.click());
      zone.addEventListener('dragover', (e) => {
        e.preventDefault();
        zone.classList.add('dragover');
      });
      zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
      zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('dragover');
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
          handleFile(e.dataTransfer.files[0]);
        }
      });
      input.addEventListener('change', (e) => {
        if (e.target.files && e.target.files[0]) {
          handleFile(e.target.files[0]);
        }
      });

      function handleFile(file) {
        const reader = new FileReader();
        reader.onload = (ev) => {
          const dataUrl = ev.target.result;
          if (preview) {
            preview.src = dataUrl;
            preview.style.display = 'block';
          }
          onLoaded(dataUrl, file);
        };
        reader.readAsDataURL(file);
      }
    }

    bindImageUpload('zoneVideoFirstImg', 'inputVideoFirstImg', 'prevVideoFirstImg', (url) => {
      videoSdkFirstImgDataUrl = url;
      appendLog('已加载视频首帧/封面参考图');
    });
    bindImageUpload('zoneVideoLastImg', 'inputVideoLastImg', 'prevVideoLastImg', (url) => {
      videoSdkLastImgDataUrl = url;
      appendLog('已加载视频尾帧参考图 (首尾帧过渡模式)');
    });
    bindImageUpload('zoneGridRefImg', 'inputGridRefImg', 'prevGridRefImg', (url) => {
      gridSdkRefImgDataUrl = url;
      appendLog('已加载宫格生成角色锁脸参考图');
    });

    // 动作源媒体上传
    const zoneGridMotion = document.getElementById('zoneGridMotion');
    const inputGridMotion = document.getElementById('inputGridMotion');
    const motionFileName = document.getElementById('motionFileName');
    if (zoneGridMotion && inputGridMotion) {
      zoneGridMotion.addEventListener('click', () => inputGridMotion.click());
      inputGridMotion.addEventListener('change', (e) => {
        if (e.target.files && e.target.files[0]) {
          gridSdkMotionFile = e.target.files[0];
          if (motionFileName) motionFileName.textContent = '已选择动作源: ' + gridSdkMotionFile.name;
          appendLog('已加载动作迁移源媒体: ' + gridSdkMotionFile.name);
        }
      });
    }

    // 4. Tab 3: 本地视频 + 自定义封面上传与时间轴剪辑 (对齐并增强 W4J1e/Video2LivePhoto)
    const zoneLocalVideo = document.getElementById('zoneLocalVideo');
    const inputLocalVideo = document.getElementById('inputLocalVideo');
    const localVideoPlayer = document.getElementById('localVideoPlayer');
    const trimSection = document.getElementById('localVideoTrimSection');
    const startSlider = document.getElementById('trimStartSlider');
    const endSlider = document.getElementById('trimEndSlider');
    const startValText = document.getElementById('trimStartVal');
    const endValText = document.getElementById('trimEndVal');
    const trimDurBadge = document.getElementById('trimDurationBadge');
    const coverThumbPreview = document.getElementById('localCoverPreview');

    if (zoneLocalVideo && inputLocalVideo) {
      zoneLocalVideo.addEventListener('click', () => inputLocalVideo.click());
      zoneLocalVideo.addEventListener('dragover', (e) => {
        e.preventDefault();
        zoneLocalVideo.classList.add('dragover');
      });
      zoneLocalVideo.addEventListener('dragleave', () => zoneLocalVideo.classList.remove('dragover'));
      zoneLocalVideo.addEventListener('drop', (e) => {
        e.preventDefault();
        zoneLocalVideo.classList.remove('dragover');
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
          handleLocalVideoSelect(e.dataTransfer.files[0]);
        }
      });
      inputLocalVideo.addEventListener('change', (e) => {
        if (e.target.files && e.target.files[0]) {
          handleLocalVideoSelect(e.target.files[0]);
        }
      });
    }

    async function handleLocalVideoSelect(file) {
      const check = FileValidator.isValidFileType(file, ['video']);
      if (!check.valid) {
        showNotification(check.message, 'error');
        return;
      }
      localVideoFile = file;
      appendLog('正在加载本地视频: ' + file.name + ' (' + FileValidator.formatBytes(file.size) + ')');
      try {
        const videoEl = await videoProcessor.loadVideo(file);
        localVideoDuration = videoEl.duration && !isNaN(videoEl.duration) ? videoEl.duration : 5.0;

        if (localVideoPlayer) {
          localVideoPlayer.src = URL.createObjectURL(file);
          localVideoPlayer.style.display = 'block';
        }
        if (trimSection) {
          trimSection.style.display = 'block';
        }
        if (startSlider && endSlider) {
          startSlider.max = localVideoDuration.toFixed(1);
          startSlider.value = 0;
          endSlider.max = localVideoDuration.toFixed(1);
          const prefDur = parseFloat(document.getElementById('optLiveDuration')?.value ?? '2.0');
          const initEnd = prefDur > 0 ? Math.min(prefDur, localVideoDuration) : localVideoDuration;
          endSlider.value = initEnd.toFixed(1);
          updateTrimLabels();
        }

        const firstCover = await videoProcessor.extractCoverFrame(0.05);
        localCoverBlob = firstCover;
        livePhotoBuilder.setCoverImage(firstCover);
        if (coverThumbPreview) {
          coverThumbPreview.src = URL.createObjectURL(firstCover);
          coverThumbPreview.style.display = 'block';
        }
        showNotification('视频已就绪，已自动提取首帧作为实况封面', 'success');
      } catch (err) {
        appendLog('视频解码提示: ' + err.message);
        showNotification(err.message, 'warning');
      }
    }

    function updateTrimLabels() {
      if (!startSlider || !endSlider) return;
      let s = parseFloat(startSlider.value) || 0;
      let e = parseFloat(endSlider.value) || localVideoDuration;
      if (s >= e) {
        s = Math.max(0, e - 0.5);
        startSlider.value = s;
      }
      if (startValText) startValText.textContent = formatTime(s);
      if (endValText) endValText.textContent = formatTime(e);
      const isTrimmed = s > 0.05 || e < localVideoDuration - 0.05;
      if (trimDurBadge) {
        trimDurBadge.textContent = isTrimmed
          ? '裁剪片段: ' + (e - s).toFixed(1) + 's (重编码保留音轨)'
          : '全片直通: ' + localVideoDuration.toFixed(1) + 's (无损保留原视频与原声)';
      }
    }

    startSlider?.addEventListener('input', () => {
      updateTrimLabels();
      if (localVideoPlayer) localVideoPlayer.currentTime = parseFloat(startSlider.value) || 0;
    });
    endSlider?.addEventListener('input', updateTrimLabels);

    document.getElementById('btnCaptureVideoCover')?.addEventListener('click', async () => {
      if (!localVideoFile) {
        showNotification('请先上传视频文件', 'warning');
        return;
      }
      try {
        const curT = localVideoPlayer ? localVideoPlayer.currentTime : 0;
        const blob = await videoProcessor.extractCoverFrame(curT);
        localCoverBlob = blob;
        livePhotoBuilder.setCoverImage(blob);
        if (coverThumbPreview) {
          coverThumbPreview.src = URL.createObjectURL(blob);
          coverThumbPreview.style.display = 'block';
        }
        appendLog('已截取视频 ' + curT.toFixed(2) + 's 画面作为实况封面');
        showNotification('已将当前帧设为实况封面！', 'success');
      } catch (err) {
        showNotification('截帧失败: ' + err.message, 'error');
      }
    });

    const inputCustomCover = document.getElementById('inputCustomCover');
    document.getElementById('btnUploadCustomCover')?.addEventListener('click', () => inputCustomCover?.click());
    inputCustomCover?.addEventListener('change', (e) => {
      if (e.target.files && e.target.files[0]) {
        const f = e.target.files[0];
        localCoverBlob = f;
        livePhotoBuilder.setCoverImage(f);
        if (coverThumbPreview) {
          coverThumbPreview.src = URL.createObjectURL(f);
          coverThumbPreview.style.display = 'block';
        }
        appendLog('已设置自定义实况封面照片: ' + f.name);
        showNotification('自定义封面设置成功！', 'success');
      }
    });

    // 5. Tab 4: 本地宫格图上传与内置示例宫格生成器
    bindImageUpload('zoneLocalGrid', 'inputLocalGrid', 'prevLocalGrid', async (dataUrl) => {
      await processGridDataUrlToLive(dataUrl, 'local_grid');
    });

    function createDemoSpriteGridDataUrl(gridLayout = '3x3') {
      const is16 = gridLayout === '4x4';
      const n = is16 ? 4 : 3;
      const total = n * n;
      const cell = 320;
      const border = 6;
      const size = n * cell + (n - 1) * border;
      const canvas = document.createElement('canvas');
      canvas.width = size;
      canvas.height = size;
      const ctx = canvas.getContext('2d');
      ctx.fillStyle = '#FFFFFF';
      ctx.fillRect(0, 0, size, size);

      for (let i = 0; i < total; i++) {
        const r = Math.floor(i / n);
        const c = i % n;
        const ox = c * (cell + border);
        const oy = r * (cell + border);
        const phase = (i / total) * Math.PI * 2;

        ctx.fillStyle = '#FFFDF9';
        ctx.fillRect(ox, oy, cell, cell);

        const cx = ox + cell / 2;
        const cy = oy + cell / 2 + Math.sin(phase) * 6;

        const grad = ctx.createRadialGradient(cx, cy - 10, 15, cx, cy, 125);
        grad.addColorStop(0, 'rgba(251, 191, 36, 0.28)');
        grad.addColorStop(1, 'rgba(251, 191, 36, 0)');
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(cx, cy, 125, 0, Math.PI * 2);
        ctx.fill();

        const earTilt = Math.sin(phase) * 0.16;
        ctx.save();
        ctx.translate(cx - 48, cy - 58);
        ctx.rotate(-0.35 + earTilt);
        ctx.fillStyle = '#F59E0B';
        ctx.beginPath();
        ctx.ellipse(0, 0, 22, 42, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#FDE68A';
        ctx.beginPath();
        ctx.ellipse(0, 4, 11, 26, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();

        ctx.save();
        ctx.translate(cx + 48, cy - 58);
        ctx.rotate(0.35 - earTilt);
        ctx.fillStyle = '#F59E0B';
        ctx.beginPath();
        ctx.ellipse(0, 0, 22, 42, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#FDE68A';
        ctx.beginPath();
        ctx.ellipse(0, 4, 11, 26, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();

        ctx.fillStyle = '#FBBF24';
        ctx.beginPath();
        ctx.roundRect(cx - 52, cy + 28, 104, 72, 34);
        ctx.fill();

        ctx.fillStyle = '#EF4444';
        ctx.beginPath();
        ctx.roundRect(cx - 54, cy + 24, 108, 22, 11);
        ctx.fill();

        const waveAngle = -0.6 + Math.sin(phase) * 0.55;
        ctx.save();
        ctx.translate(cx + 48, cy + 44);
        ctx.rotate(waveAngle);
        ctx.fillStyle = '#F59E0B';
        ctx.beginPath();
        ctx.ellipse(26, 0, 24, 13, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();

        ctx.fillStyle = '#FBBF24';
        ctx.beginPath();
        ctx.arc(cx, cy - 12, 64, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = 'rgba(244, 63, 94, 0.35)';
        ctx.beginPath();
        ctx.ellipse(cx - 36, cy - 2, 13, 8, 0, 0, Math.PI * 2);
        ctx.ellipse(cx + 36, cy - 2, 13, 8, 0, 0, Math.PI * 2);
        ctx.fill();

        const isBlink = i === Math.floor(total / 2);
        ctx.fillStyle = '#1E293B';
        if (isBlink) {
          ctx.lineWidth = 4;
          ctx.strokeStyle = '#1E293B';
          ctx.beginPath();
          ctx.arc(cx - 24, cy - 16, 9, 0.1 * Math.PI, 0.9 * Math.PI);
          ctx.stroke();
          ctx.beginPath();
          ctx.arc(cx + 24, cy - 16, 9, 0.1 * Math.PI, 0.9 * Math.PI);
          ctx.stroke();
        } else {
          ctx.beginPath();
          ctx.arc(cx - 24, cy - 16, 8.5, 0, Math.PI * 2);
          ctx.arc(cx + 24, cy - 16, 8.5, 0, Math.PI * 2);
          ctx.fill();
          ctx.fillStyle = '#FFFFFF';
          ctx.beginPath();
          ctx.arc(cx - 21, cy - 19, 3, 0, Math.PI * 2);
          ctx.arc(cx + 27, cy - 19, 3, 0, Math.PI * 2);
          ctx.fill();
        }

        ctx.strokeStyle = '#92400E';
        ctx.lineWidth = 3.5;
        ctx.beginPath();
        ctx.arc(cx, cy - 4, 11 + Math.sin(phase) * 2, 0.15 * Math.PI, 0.85 * Math.PI);
        ctx.stroke();
      }
      return canvas.toDataURL('image/jpeg', 0.95);
    }

    document.getElementById('btnLoadDemoGrid')?.addEventListener('click', async () => {
      const gridLayout = document.getElementById('optGridLayout')?.value || '3x3';
      appendLog('正在加载内置示例 ' + gridLayout + ' 宫格图并合成实况照片...');
      let dataUrl = null;
      try {
        const samplePath = gridLayout === '4x4' ? '../examples/sample_grid_4x4.jpg' : '../examples/sample_grid_3x3.jpg';
        const resp = await fetch(samplePath);
        if (resp.ok) {
          const blob = await resp.blob();
          dataUrl = await new Promise((res) => {
            const fr = new FileReader();
            fr.onload = (e) => res(e.target.result);
            fr.readAsDataURL(blob);
          });
        }
      } catch (_e) {}
      if (!dataUrl) {
        dataUrl = createDemoSpriteGridDataUrl(gridLayout);
      }
      const prev = document.getElementById('prevLocalGrid');
      if (prev) {
        prev.src = dataUrl;
        prev.style.display = 'block';
      }
      await processGridDataUrlToLive(dataUrl, 'demo_' + gridLayout);
    });

    // 6. 将宫格图 (支持远程 URL / DataURL / Blob) 切分并合成为 Live Photo
    async function processGridDataUrlToLive(dataUrlOrBlob, baseName = 'grid_live') {
      const gridLayout = document.getElementById('optGridLayout')?.value || '3x3';
      const transparent = document.getElementById('optTransparent')?.checked || false;
      const backdrop = document.getElementById('optBackdrop')?.value || '#FFFFFF';
      const loopMode = document.getElementById('optLoopMode')?.value || 'pingpong';
      const fps = parseInt(document.getElementById('optFps')?.value || '16', 10);
      const format = document.getElementById('optExportFormat')?.value || 'both';

      setBusy(true, '正在自适应切分宫格并合成实况视频流...');
      try {
        let localSource = dataUrlOrBlob;
        if (typeof dataUrlOrBlob === 'string' && /^https?:\/\//i.test(dataUrlOrBlob)) {
          appendLog('正在通过跨域桥拉取生成的宫格原图...');
          localSource = await HrioWebClient.fetchRemoteMediaBlob(dataUrlOrBlob, 'image/jpeg');
        }
        const img = await LivePhotoBuilder.loadImageFromBlob(localSource);
        const sliced = sliceGridCanvas(img, gridLayout, transparent, backdrop);
        currentSlicedCanvases = sliced.canvases;
        currentSlicedUrls = sliced.dataUrls;
        selectedCoverFrameIdx = 0;

        renderFramesGallery(currentSlicedUrls, selectedCoverFrameIdx, async (newCoverIdx) => {
          selectedCoverFrameIdx = newCoverIdx;
          appendLog('已切换第 #' + (newCoverIdx + 1) + ' 帧作为实况照片封面，正在重新打包...');
          await rebuildLiveFromCurrentSlices(baseName);
        });

        await rebuildLiveFromCurrentSlices(baseName, { fps, loopMode, backdrop, format });
        showNotification('宫格切分转实况照片完成！按住右侧 LIVE 舞台即可播放', 'success');
      } catch (err) {
        console.error(err);
        appendLog('❌ 处理失败: ' + err.message);
        showNotification('处理失败: ' + err.message, 'error');
      } finally {
        setBusy(false);
      }
    }

    async function rebuildLiveFromCurrentSlices(baseName = 'grid_live', opts = {}) {
      if (!currentSlicedCanvases.length) return;
      const backdrop = opts.backdrop || document.getElementById('optBackdrop')?.value || '#FFFFFF';
      const loopMode = opts.loopMode || document.getElementById('optLoopMode')?.value || 'pingpong';
      const fps = opts.fps || parseInt(document.getElementById('optFps')?.value || '16', 10);
      const format = opts.format || document.getElementById('optExportFormat')?.value || 'both';

      appendLog('正在编码实况视频流 (fps=' + fps + ', 循环=' + loopMode + ', 帧间插值=开启)...');
      const liveVideoBlob = await videoProcessor.framesToLiveVideoBlob(currentSlicedCanvases, {
        fps,
        minDurationSec: parseFloat(document.getElementById('optLiveDuration')?.value || '2.0') || 2.0,
        loopMode,
        crossfadeSteps: 1,
        backdrop,
      });

      const coverCanvas = currentSlicedCanvases[selectedCoverFrameIdx] || currentSlicedCanvases[0];
      const coverBlob = await new Promise((res) => coverCanvas.toBlob(res, 'image/jpeg', 0.95));

      livePhotoBuilder.setCoverImage(coverBlob);
      livePhotoBuilder.setDirectVideoBlob(liveVideoBlob);
      const bundle = await livePhotoBuilder.build(format, baseName, backdrop);

      if (typeof gifshot !== 'undefined' && currentSlicedUrls.length > 0) {
        try {
          const gifDataUrl = await new Promise((res, rej) => {
            gifshot.createGIF(
              {
                images: currentSlicedUrls,
                gifWidth: 320,
                gifHeight: 320,
                interval: 1 / Math.max(6, Math.min(20, fps)),
                numFrames: currentSlicedUrls.length,
              },
              (obj) => (!obj.error ? res(obj.image) : rej(new Error(obj.errorMsg)))
            );
          });
          bundle.gifDataUrl = gifDataUrl;
        } catch (_e) {}
      }

      updateLiveStageWithBundle(bundle);
    }

    function renderFramesGallery(urls, activeIdx, onSelectFrame) {
      const gridEl = document.getElementById('framesGrid');
      const titleEl = document.getElementById('framesTitle');
      if (!gridEl) return;
      gridEl.innerHTML = '';
      if (titleEl) {
        titleEl.textContent = '🧩 宫格序列帧 (' + urls.length + ' 帧 · 点击任意帧设为实况封面)';
      }
      urls.forEach((u, idx) => {
        const item = document.createElement('div');
        item.className = 'frame-thumb' + (idx === activeIdx ? ' active-cover' : '');
        item.title = '点击将第 ' + (idx + 1) + ' 帧设为实况照片静态封面';
        const im = document.createElement('img');
        im.src = u;
        const badge = document.createElement('span');
        badge.className = 'frame-badge';
        badge.textContent = idx === activeIdx ? '📸 封面 #' + (idx + 1) : '#' + (idx + 1);
        item.appendChild(im);
        item.appendChild(badge);
        item.onclick = () => {
          gridEl.querySelectorAll('.frame-thumb').forEach((el, i) => {
            el.classList.toggle('active-cover', i === idx);
            const b = el.querySelector('.frame-badge');
            if (b) b.textContent = i === idx ? '📸 封面 #' + (i + 1) : '#' + (i + 1);
          });
          if (onSelectFrame) onSelectFrame(idx);
        };
        gridEl.appendChild(item);
      });
    }

    // 7. 将任意远程视频 URL 转换为完整实况照片产物包 (支持跨域无损拉取 + 抽帧封面 + XMP注入)
    async function convertRemoteVideoUrlToLive(videoUrl, baseName = 'sdk_video_live') {
      const format = document.getElementById('optExportFormat')?.value || 'both';
      const backdrop = document.getElementById('optBackdrop')?.value || '#FFFFFF';
      const useRefCover = document.getElementById('videoUseRefCoverCheck')?.checked ?? true;

      const directInput = document.getElementById('directVideoUrlInput');
      if (directInput) directInput.value = videoUrl;

      appendLog('⬇️ 正在无损拉取视频二进制流: ' + videoUrl);
      setBusy(true, '正在通过跨域桥无损拉取视频流并提取实况封面...');

      const liveDur = parseFloat(document.getElementById('optLiveDuration')?.value ?? '2.0');
      const videoBlob = await HrioWebClient.fetchRemoteMediaBlob(videoUrl, 'video/mp4', { duration: liveDur > 0 ? liveDur : 0 });
      appendLog('✅ 实况视频流已就绪 (' + (liveDur > 0 ? '已自动截取黄金 ' + liveDur.toFixed(1) + 's · ' : '') + FileValidator.formatBytes(videoBlob.size) + ')，正在提取封面与注入 XMP...');

      let coverBlob = null;
      if (useRefCover && videoSdkFirstImgDataUrl) {
        coverBlob = await HrioWebClient.fetchRemoteMediaBlob(videoSdkFirstImgDataUrl, 'image/jpeg');
      } else {
        await videoProcessor.loadVideo(videoBlob);
        coverBlob = await videoProcessor.extractCoverFrame(0.05);
      }

      livePhotoBuilder.setCoverImage(coverBlob);
      livePhotoBuilder.setDirectVideoBlob(videoBlob);
      const bundle = await livePhotoBuilder.build(format, baseName, backdrop);
      updateLiveStageWithBundle(bundle);
      showNotification('实况照片 (.jpg + .zip) 制作成功！按住右侧 LIVE 舞台即可播放', 'success');
      return bundle;
    }

    // 绑定「⚡ 立即将该视频链接合成实况照片」按钮
    document.getElementById('btnConvertDirectVideoUrl')?.addEventListener('click', async () => {
      const directUrl = document.getElementById('directVideoUrlInput')?.value.trim() || '';
      if (!directUrl) {
        showNotification('请先粘贴视频 URL', 'warning');
        return;
      }
      try {
        await convertRemoteVideoUrlToLive(directUrl, 'veo3_video_live');
      } catch (err) {
        console.error(err);
        appendLog('❌ 视频链接转实况失败: ' + err.message);
        showNotification('转换失败: ' + err.message, 'error');
      } finally {
        setBusy(false);
      }
    });

    // 8. 更新右侧 iOS 风格 LIVE 实况交互预览舞台
    function updateLiveStageWithBundle(bundle) {
      currentResultBundle = bundle;
      const emptyHint = document.getElementById('stageEmptyHint');
      const livePlayerWrap = document.getElementById('livePlayerWrap');
      const coverImg = document.getElementById('liveStageCover');
      const videoEl = document.getElementById('liveStageVideo');
      const telemetryBar = document.getElementById('liveTelemetryBar');
      const downloadActions = document.getElementById('downloadActions');

      if (emptyHint) emptyHint.style.display = 'none';
      if (livePlayerWrap) livePlayerWrap.style.display = 'block';
      if (downloadActions) downloadActions.style.display = 'flex';

      const coverUrl = URL.createObjectURL(bundle.coverJpgBlob);
      const videoUrl = URL.createObjectURL(bundle.videoMp4Blob);
      if (coverImg) coverImg.src = coverUrl;
      if (videoEl) {
        videoEl.src = videoUrl;
        videoEl.load();
      }

      const insp = bundle.inspection || {};
      if (telemetryBar) {
        telemetryBar.style.display = 'grid';
        document.getElementById('statTotalSize').textContent = FileValidator.formatBytes(insp.totalBytes || bundle.motionJpgBlob.size);
        document.getElementById('statCoverSize').textContent = FileValidator.formatBytes(insp.coverBytes || bundle.coverJpgBlob.size);
        document.getElementById('statVideoSize').textContent = FileValidator.formatBytes(insp.videoBytes || bundle.videoMp4Blob.size);
        document.getElementById('statXmpStatus').textContent = insp.valid ? '✅ XMP v1/v2 + 视频流已就绪' : '✅ 已注入 XMP';
      }

      const triggerDownload = (blobOrUrl, filename) => {
        if (!blobOrUrl) return;
        if (typeof saveAs !== 'undefined' && blobOrUrl instanceof Blob) {
          saveAs(blobOrUrl, filename);
          return;
        }
        const a = document.createElement('a');
        a.href = typeof blobOrUrl === 'string' ? blobOrUrl : URL.createObjectURL(blobOrUrl);
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
      };

      const btnDlMotionJpg = document.getElementById('btnDlMotionJpg');
      if (btnDlMotionJpg) {
        btnDlMotionJpg.onclick = () => triggerDownload(bundle.motionJpgBlob, bundle.motionJpgFileName);
      }
      const btnDlAppleZip = document.getElementById('btnDlAppleZip');
      if (btnDlAppleZip) {
        btnDlAppleZip.style.display = bundle.appleZipBlob ? 'inline-flex' : 'none';
        btnDlAppleZip.onclick = () => triggerDownload(bundle.appleZipBlob, bundle.appleZipFileName);
      }
      const btnDlMp4 = document.getElementById('btnDlMp4');
      if (btnDlMp4) {
        btnDlMp4.onclick = () => triggerDownload(bundle.videoMp4Blob, bundle.videoMp4FileName);
      }
      const btnDlCover = document.getElementById('btnDlCover');
      if (btnDlCover) {
        btnDlCover.onclick = () => triggerDownload(bundle.coverJpgBlob, bundle.coverJpgFileName);
      }
      const btnDlGif = document.getElementById('btnDlGif');
      if (btnDlGif) {
        btnDlGif.style.display = bundle.gifDataUrl ? 'inline-flex' : 'none';
        btnDlGif.onclick = () => triggerDownload(bundle.gifDataUrl, bundle.motionJpgFileName.replace('_live.jpg', '.gif'));
      }

      appendLog(
        '✅ 实况照片构建完成: ' +
          bundle.motionJpgFileName +
          ' (总计 ' +
          FileValidator.formatBytes(bundle.motionJpgBlob.size) +
          ')'
      );
    }

    // 9. iOS 风格 LIVE 实况播放器交互 (按住 / 悬停 / 点击播放实况与声音)
    const livePlayerWrap = document.getElementById('livePlayerWrap');
    const liveStageVideo = document.getElementById('liveStageVideo');
    const btnPlayLiveToggle = document.getElementById('btnPlayLiveToggle');
    const soundBadge = document.getElementById('liveSoundBadge');
    let soundMuted = false;

    function startLivePlayback() {
      if (!liveStageVideo || !liveStageVideo.src) return;
      isPlayingLive = true;
      livePlayerWrap?.classList.add('playing');
      liveStageVideo.muted = soundMuted;
      liveStageVideo.currentTime = 0;
      liveStageVideo.play().catch(() => {
        liveStageVideo.muted = true;
        liveStageVideo.play().catch(() => {});
      });
    }

    function stopLivePlayback() {
      if (!liveStageVideo) return;
      isPlayingLive = false;
      livePlayerWrap?.classList.remove('playing');
      liveStageVideo.pause();
      liveStageVideo.currentTime = 0;
    }

    if (livePlayerWrap) {
      livePlayerWrap.addEventListener('mousedown', startLivePlayback);
      livePlayerWrap.addEventListener('mouseup', stopLivePlayback);
      livePlayerWrap.addEventListener('mouseleave', stopLivePlayback);
      livePlayerWrap.addEventListener('touchstart', (e) => {
        e.preventDefault();
        startLivePlayback();
      });
      livePlayerWrap.addEventListener('touchend', stopLivePlayback);
    }

    if (liveStageVideo) {
      liveStageVideo.addEventListener('ended', () => {
        stopLivePlayback();
      });
    }

    if (btnPlayLiveToggle) {
      btnPlayLiveToggle.addEventListener('click', () => {
        if (isPlayingLive) stopLivePlayback();
        else startLivePlayback();
      });
    }

    if (soundBadge) {
      soundBadge.addEventListener('click', (e) => {
        e.stopPropagation();
        soundMuted = !soundMuted;
        soundBadge.textContent = soundMuted ? '🔇 静音' : '🔊 原声';
        if (liveStageVideo) liveStageVideo.muted = soundMuted;
      });
    }

    // 10. 主生成按钮逻辑分发
    const btnMainAction = document.getElementById('btnMainGenerate');
    function setBusy(busy, statusMsg = '') {
      if (btnMainAction) {
        btnMainAction.disabled = busy;
        btnMainAction.innerHTML = busy
          ? '<span class="spinner"></span> <span>' + (statusMsg || '正在处理中...') + '</span>'
          : '<span>🚀 一键生成实况照片 (Live Photo)</span>';
      }
      const statusEl = document.getElementById('stageStatusText');
      if (statusEl && statusMsg) statusEl.textContent = statusMsg;
    }

    btnMainAction?.addEventListener('click', async () => {
      const apiKey = document.getElementById('apiKeyInput')?.value || '';
      const baseUrl = document.getElementById('baseUrlInput')?.value || 'https://hrioapi.hrio.site/v1';
      const format = document.getElementById('optExportFormat')?.value || 'both';
      const backdrop = document.getElementById('optBackdrop')?.value || '#FFFFFF';

      try {
        // 分支 A: SDK 视频直生转实况图
        if (activeTab === 'video-sdk') {
          const client = new HrioWebClient(apiKey, baseUrl);
          const videoModel = document.getElementById('videoModelSelect')?.value || 'veo-3.0-fast-generate-001';
          const userPrompt = document.getElementById('videoSdkPrompt')?.value.trim() || 'gentle breeze blowing hair, natural eye blink and warm smile';
          const aspectRatio = document.getElementById('videoAspectSelect')?.value || '9:16';
          const duration = parseInt(document.getElementById('videoDurationSelect')?.value || '8', 10);
          const genAudio = document.getElementById('videoAudioCheck')?.checked ?? true;

          const refImgs = [];
          if (videoSdkFirstImgDataUrl) refImgs.push(videoSdkFirstImgDataUrl);
          if (videoSdkLastImgDataUrl) refImgs.push(videoSdkLastImgDataUrl);

          const fullPrompt = buildVideoLivePrompt(
            userPrompt,
            selectedVideoPreset,
            'Cinematic live photo, ultra-high definition, natural lighting, authentic texture',
            Boolean(videoSdkFirstImgDataUrl),
            Boolean(videoSdkLastImgDataUrl)
          );

          setBusy(true, '正在请求 SDK 视频生成 (' + videoModel + ')...');
          appendLog('🎬 开始请求 SDK 视频生成: ' + videoModel + ' (自动匹配模型标准契约参数)');

          const videoUrl = await client.generateVideo({
            model: videoModel,
            prompt: fullPrompt,
            images: refImgs,
            aspectRatio,
            duration,
            generateAudio: genAudio,
            onProgress: (st, pct) => {
              const pText = pct != null ? ' (' + pct + '%)' : '';
              setBusy(true, 'SDK 视频生成中: ' + st + pText);
            },
          });

          await convertRemoteVideoUrlToLive(videoUrl, 'sdk_video_live');
          return;
        }

        // 分支 B: SDK 宫格生图切分转实况图
        if (activeTab === 'grid-sdk') {
          const client = new HrioWebClient(apiKey, baseUrl);
          const imageModel = document.getElementById('imageModelSelect')?.value || 'gemini-nano-banana-2.1';
          const userPrompt = document.getElementById('gridSdkPrompt')?.value.trim() || '可爱的3D角色温柔微笑挥手';
          const gridLayout = document.getElementById('optGridLayout')?.value || '3x3';
          const is4k = document.getElementById('opt4k')?.checked || false;
          const reqSize = is4k ? '4096x4096' : '1024x1024';

          let fullPrompt = '';
          let imagesPayload = [];

          if (gridSdkMotionFile && gridSdkRefImgDataUrl) {
            setBusy(true, '正在从源媒体提取动作参考网格...');
            const guideDataUrl = await createMotionGuideDataUrl(gridSdkMotionFile, gridLayout);
            imagesPayload = [gridSdkRefImgDataUrl, guideDataUrl];
            fullPrompt = buildMotionTransferPrompt(userPrompt, gridLayout, 'Preserve target character art style, clean solid white background', is4k);
          } else {
            if (gridSdkRefImgDataUrl) imagesPayload = [gridSdkRefImgDataUrl];
            fullPrompt = buildGridLivePrompt(
              userPrompt,
              selectedGridPreset,
              gridLayout,
              'High-end 3D animation render, soft ambient lighting, clean solid white background',
              Boolean(gridSdkRefImgDataUrl),
              is4k
            );
          }

          setBusy(true, '正在请求 SDK 生成 ' + gridLayout + ' 宫格序列图 (' + imageModel + ')...');
          appendLog('🧩 开始请求 SDK 宫格生图: ' + imageModel + ' (' + reqSize + ')');

          const imgUrlOrData = await client.generateImage({
            model: imageModel,
            prompt: fullPrompt,
            images: imagesPayload,
            size: reqSize,
          });

          const prev = document.getElementById('prevLocalGrid');
          if (prev) {
            prev.src = imgUrlOrData;
            prev.style.display = 'block';
          }

          await processGridDataUrlToLive(imgUrlOrData, 'sdk_grid_live');
          return;
        }

        // 分支 C: 本地视频 + 自定义封面转实况图
        if (activeTab === 'local-vid') {
          if (!localVideoFile) {
            showNotification('请先在左侧选择或拖入本地视频文件！', 'warning');
            return;
          }
          const startTime = parseFloat(startSlider?.value || '0') || 0;
          const endTime = parseFloat(endSlider?.value || String(localVideoDuration)) || localVideoDuration;
          const preserveAudio = document.getElementById('localPreserveAudioCheck')?.checked ?? true;
          const isTrimmed = startTime > 0.05 || endTime < localVideoDuration - 0.05;

          videoProcessor.isTrimmed = isTrimmed;
          if (!localCoverBlob) {
            localCoverBlob = await videoProcessor.extractCoverFrame(startTime);
          }
          livePhotoBuilder.setCoverImage(localCoverBlob);

          if (!isTrimmed && preserveAudio) {
            appendLog('检测到未剪辑，直接采用原始视频流（无损保留画质与原视频声音）');
            livePhotoBuilder.setDirectVideoBlob(localVideoFile);
          } else {
            setBusy(true, '正在截取视频片段 (' + formatTime(startTime) + ' - ' + formatTime(endTime) + ') 并合成音轨...');
            livePhotoBuilder.setDirectVideoBlob(null);
            const frames = await videoProcessor.extractFrames(startTime, endTime, 24, (p) => {
              setBusy(true, '正在提取视频帧... ' + p + '%');
            });
            const trimmedBlob = await videoProcessor.convertToMP4(frames, endTime - startTime, preserveAudio);
            livePhotoBuilder.setDirectVideoBlob(trimmedBlob);
          }

          setBusy(true, '正在封装实况照片...');
          const bundle = await livePhotoBuilder.build(format, 'local_video_live', backdrop);
          updateLiveStageWithBundle(bundle);
          showNotification('本地视频转实况照片成功！', 'success');
          return;
        }

        // 分支 D: 本地宫格大图离线切分转实况图
        if (activeTab === 'local-grd') {
          const prev = document.getElementById('prevLocalGrid');
          if (prev && prev.src && prev.style.display !== 'none') {
            await processGridDataUrlToLive(prev.src, 'local_grid_live');
          } else {
            document.getElementById('btnLoadDemoGrid')?.click();
          }
          return;
        }

        // 分支 E: 实况图验真器
        if (activeTab === 'inspector') {
          if (currentResultBundle && currentResultBundle.motionJpgBlob) {
            await runInspectorOnBlob(currentResultBundle.motionJpgBlob, currentResultBundle.motionJpgFileName);
          } else {
            showNotification('请先上传一张 .jpg 实况照片，或先生成一张实况图！', 'info');
          }
        }
      } catch (err) {
        console.error(err);
        appendLog('❌ 错误: ' + err.message);
        showNotification(err.message, 'error');
      } finally {
        setBusy(false);
      }
    });

    // 11. Tab 5: 实况图逆向验真与解包器 (Inspector)
    const zoneInspect = document.getElementById('zoneInspector');
    const inputInspect = document.getElementById('inputInspector');
    if (zoneInspect && inputInspect) {
      zoneInspect.addEventListener('click', () => inputInspect.click());
      zoneInspect.addEventListener('dragover', (e) => {
        e.preventDefault();
        zoneInspect.classList.add('dragover');
      });
      zoneInspect.addEventListener('dragleave', () => zoneInspect.classList.remove('dragover'));
      zoneInspect.addEventListener('drop', (e) => {
        e.preventDefault();
        zoneInspect.classList.remove('dragover');
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
          runInspectorOnBlob(e.dataTransfer.files[0], e.dataTransfer.files[0].name);
        }
      });
      inputInspect.addEventListener('change', (e) => {
        if (e.target.files && e.target.files[0]) {
          runInspectorOnBlob(e.target.files[0], e.target.files[0].name);
        }
      });
    }

    document.getElementById('btnInspectCurrent')?.addEventListener('click', () => {
      if (!currentResultBundle || !currentResultBundle.motionJpgBlob) {
        showNotification('当前尚未生成实况照片，正在为您自动生成示例实况图并验真...', 'info');
        document.getElementById('btnLoadDemoGrid')?.click();
        setTimeout(() => {
          if (currentResultBundle && currentResultBundle.motionJpgBlob) {
            runInspectorOnBlob(currentResultBundle.motionJpgBlob, currentResultBundle.motionJpgFileName);
          }
        }, 2800);
        return;
      }
      runInspectorOnBlob(currentResultBundle.motionJpgBlob, currentResultBundle.motionJpgFileName);
    });

    async function runInspectorOnBlob(blob, fileName = 'livephoto.jpg') {
      const ab = await blob.arrayBuffer();
      const info = LivePhotoBuilder.inspectMotionPhoto(ab);
      const reportEl = document.getElementById('inspectorReport');
      if (reportEl) {
        reportEl.style.display = 'block';
        reportEl.innerHTML =
          '<div class="insp-row"><span>📄 文件名:</span><strong>' + fileName + '</strong></div>' +
          '<div class="insp-row"><span>🔍 实况有效性:</span><strong style="color:' + (info.valid ? '#34d399' : '#f87171') + '">' +
          (info.valid ? '✅ 标准 Google Motion Photo (含 XMP + 内嵌视频流)' : '❌ 未检测到完整实况视频流') +
          '</strong></div>' +
          '<div class="insp-row"><span>🏷️ XMP 元数据:</span><strong>' + (info.hasXmp ? 'GCamera:MotionPhoto=1 / MicroVideo=1' : '缺失') + '</strong></div>' +
          '<div class="insp-row"><span>🎬 视频封装签名:</span><strong>' + info.containerSignature + '</strong></div>' +
          '<div class="insp-row"><span>📐 字节分割点 (Offset):</span><strong>' + info.splitPosition + ' B (封面 ' + FileValidator.formatBytes(info.coverBytes) + ' + 视频 ' + FileValidator.formatBytes(info.videoBytes) + ')</strong></div>';
      }
      if (info.valid && info.coverBlob && info.videoBlob) {
        updateLiveStageWithBundle({
          motionJpgBlob: blob,
          motionJpgFileName: fileName,
          appleZipBlob: null,
          appleZipFileName: '',
          coverJpgBlob: info.coverBlob,
          coverJpgFileName: 'extracted_cover.jpg',
          videoMp4Blob: info.videoBlob,
          videoMp4FileName: 'extracted_video.mp4',
          inspection: info,
        });
        showNotification('实况照片验真通过！已拆解出封面与内嵌视频并同步至右侧播放台', 'success');
      } else {
        showNotification(info.reason || '该文件不包含内嵌实况视频流', 'warning');
      }
    }
  });
})();
