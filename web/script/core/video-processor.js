/**
 * banano2live - 浏览器端视频处理与宫格帧视频流编码器
 * 借鉴并升级 W4J1e/Video2LivePhoto/script/core/video-processor.js：
 *   1. 支持本地视频加载、时长/分辨率解析、HEVC 原始视频直通兜底；
 *   2. 支持任意时间点高清静态封面抽帧 (extractCoverFrame)；
 *   3. 支持视频时间轴裁剪抽帧 + 原始音轨捕获合并 (convertToMP4)；
 *   4. 新增支持将 3x3 (9帧) / 4x4 (16帧) 宫格切片 Canvas 序列通过乒乓循环 + 帧间平滑插值
 *      实时编码为实况照片专用的 MP4/H.264 视频流 (framesToLiveVideoBlob)。
 */
(function (root) {

  class H264BitWriter {
    constructor() { this.bytes = []; this.cur = 0; this.bits = 0; }
    putBit(b) { this.cur = (this.cur << 1) | (b & 1); if (++this.bits === 8) { this.bytes.push(this.cur); this.cur = 0; this.bits = 0; } }
    putBits(v, n) { for (let i = n - 1; i >= 0; i--) this.putBit((v >>> i) & 1); }
    putUE(v) { let x = v + 1, l = 0; while ((x >>> l) > 1) l++; for (let i = 0; i < l; i++) this.putBit(0); this.putBits(x, l + 1); }
    putSE(v) { this.putUE(v <= 0 ? -2 * v : 2 * v - 1); }
    alignZero() { while (this.bits !== 0) this.putBit(0); }
    rbspTrailing() { this.putBit(1); this.alignZero(); }
    toNal() {
      const out = []; let z = 0;
      for (let i = 0; i < this.bytes.length; i++) {
        const b = this.bytes[i];
        if (z === 2 && b <= 3) { out.push(3); z = 0; }
        out.push(b);
        if (b === 0) z++; else z = 0;
      }
      return Uint8Array.from(out);
    }
  }
  function makeAvcSPS(w, h) {
    const bw = new H264BitWriter();
    bw.putBits(0x67, 8); bw.putBits(66, 8); bw.putBits(0x80, 8); bw.putBits(31, 8);
    bw.putUE(0); bw.putUE(0); bw.putUE(2); bw.putUE(0); bw.putBit(0);
    bw.putUE((w >> 4) - 1); bw.putUE((h >> 4) - 1);
    bw.putBit(1); bw.putBit(0); bw.putBit(0); bw.putBit(0);
    bw.rbspTrailing();
    return bw.toNal();
  }
  function makeAvcPPS() {
    const bw = new H264BitWriter();
    bw.putBits(0x68, 8); bw.putUE(0); bw.putUE(0); bw.putBit(0); bw.putBit(0); bw.putUE(0);
    bw.putUE(0); bw.putUE(0); bw.putBit(0); bw.putBits(0, 2); bw.putSE(0); bw.putSE(0); bw.putSE(0);
    bw.putBit(0); bw.putBit(0); bw.putBit(0);
    bw.rbspTrailing();
    return bw.toNal();
  }
  function makeAvcIdrSample(w, h, rgba, id) {
    const mbW = w >> 4, mbH = h >> 4, bw = new H264BitWriter();
    bw.putBits(0x65, 8); bw.putUE(0); bw.putUE(7); bw.putUE(0); bw.putBits(0, 4); bw.putUE(id & 15);
    bw.putBit(0); bw.putBit(0); bw.putSE(0);
    for (let my = 0; my < mbH; my++) {
      for (let mx = 0; mx < mbW; mx++) {
        bw.putUE(25); bw.alignZero();
        for (let py = 0; py < 16; py++) {
          const y = (my << 4) + py;
          for (let px = 0; px < 16; px++) {
            const idx = (y * w + (mx << 4) + px) << 2;
            const r = rgba[idx], g = rgba[idx + 1], b = rgba[idx + 2];
            bw.bytes.push(Math.max(16, Math.min(235, ((66 * r + 129 * g + 25 * b + 128) >> 8) + 16)));
          }
        }
        for (let cy = 0; cy < 8; cy++) {
          const y = (my << 4) + (cy << 1);
          for (let cx = 0; cx < 8; cx++) {
            const idx = (y * w + (mx << 4) + (cx << 1)) << 2;
            const r = rgba[idx], g = rgba[idx + 1], b = rgba[idx + 2];
            bw.bytes.push(Math.max(16, Math.min(240, ((-38 * r - 74 * g + 112 * b + 128) >> 8) + 128)));
          }
        }
        for (let cy = 0; cy < 8; cy++) {
          const y = (my << 4) + (cy << 1);
          for (let cx = 0; cx < 8; cx++) {
            const idx = (y * w + (mx << 4) + (cx << 1)) << 2;
            const r = rgba[idx], g = rgba[idx + 1], b = rgba[idx + 2];
            bw.bytes.push(Math.max(16, Math.min(240, ((112 * r - 94 * g - 18 * b + 128) >> 8) + 128)));
          }
        }
      }
    }
    bw.rbspTrailing();
    const nal = bw.toNal(), l = nal.length, avcc = new Uint8Array(4 + l);
    avcc[0] = (l >>> 24) & 255; avcc[1] = (l >>> 16) & 255; avcc[2] = (l >>> 8) & 255; avcc[3] = l & 255;
    avcc.set(nal, 4);
    return avcc;
  }
  function encodeCanvasesToAvc1Mp4Blob(canvases, durationSec = 3.0, backdrop = "#FFFFFF") {
    const W = 256, H = 256, timescale = 2400;
    const n = Math.max(1, canvases.length);
    const sampleDelta = Math.max(1, Math.round((durationSec * timescale) / n));
    const actualDuration = sampleDelta * n;
    const sps = makeAvcSPS(W, H), pps = makeAvcPPS();
    const samples = [];
    const tmp = document.createElement("canvas"); tmp.width = W; tmp.height = H;
    const tctx = tmp.getContext("2d");
    for (let i = 0; i < n; i++) {
      tctx.fillStyle = backdrop || "#FFFFFF";
      tctx.fillRect(0, 0, W, H);
      tctx.drawImage(canvases[i], 0, 0, W, H);
      const rgba = tctx.getImageData(0, 0, W, H).data;
      samples.push(makeAvcIdrSample(W, H, rgba, i));
    }
    const u32 = (v) => [(v >>> 24) & 255, (v >>> 16) & 255, (v >>> 8) & 255, v & 255];
    const u16 = (v) => [(v >>> 8) & 255, v & 255];
    const sb = (s) => { const a = []; for (let i = 0; i < s.length; i++) a.push(s.charCodeAt(i) & 255); return a; };
    const box = (t, ...ps) => {
      let l = 8; for (const p of ps) l += p.length;
      const o = new Uint8Array(l); o.set(u32(l), 0);
      for (let i = 0; i < 4; i++) o[4 + i] = t.charCodeAt(i);
      let off = 8; for (const p of ps) { o.set(p, off); off += p.length; }
      return o;
    };
    const ftyp = box("ftyp", new Uint8Array([...sb("isom"), ...u32(0x00000200), ...sb("isomiso2avc1mp41")]));
    let mdatLen = 0; for (const s of samples) mdatLen += s.length;
    const mdatStart = ftyp.length + 8;
    const offsets = [], sizes = [];
    let cur = mdatStart;
    for (const s of samples) { offsets.push(cur); sizes.push(s.length); cur += s.length; }
    const mdat = new Uint8Array(8 + mdatLen);
    mdat.set(u32(8 + mdatLen), 0); mdat.set(sb("mdat"), 4);
    let pOff = 8; for (const s of samples) { mdat.set(s, pOff); pOff += s.length; }
    const avcC = box("avcC", new Uint8Array([1, sps[1], sps[2], sps[3], 0xFF, 0xE1, ...u16(sps.length), ...sps, 1, ...u16(pps.length), ...pps]));
    const avc1H = new Uint8Array(78);
    avc1H[7] = 1; avc1H[24] = (W >> 8) & 255; avc1H[25] = W & 255; avc1H[26] = (H >> 8) & 255; avc1H[27] = H & 255;
    avc1H[29] = 0x48; avc1H[33] = 0x48; avc1H[41] = 1; avc1H[75] = 0x18; avc1H[76] = 0xFF; avc1H[77] = 0xFF;
    const stsd = box("stsd", new Uint8Array([0,0,0,0, 0,0,0,1]), box("avc1", avc1H, avcC));
    const stts = box("stts", new Uint8Array([0,0,0,0, 0,0,0,1, ...u32(n), ...u32(sampleDelta)]));
    const stss = box("stss", new Uint8Array([0,0,0,0, ...u32(n), ...samples.flatMap((_, i) => u32(i + 1))]));
    const stsc = box("stsc", new Uint8Array([0,0,0,0, 0,0,0,1, ...u32(1), ...u32(1), ...u32(1)]));
    const stsz = box("stsz", new Uint8Array([0,0,0,0, 0,0,0,0, ...u32(n), ...sizes.flatMap(u32)]));
    const stco = box("stco", new Uint8Array([0,0,0,0, ...u32(n), ...offsets.flatMap(u32)]));
    const dinf = box("dinf", box("dref", new Uint8Array([0,0,0,0, 0,0,0,1]), box("url ", new Uint8Array([0,0,0,1]))));
    const minf = box("minf", box("vmhd", new Uint8Array([0,0,0,1, 0,0, 0,0,0,0,0,0])), dinf, box("stbl", stsd, stts, stss, stsc, stsz, stco));
    const mdia = box("mdia", box("mdhd", new Uint8Array([0,0,0,0, 0,0,0,0, 0,0,0,0, ...u32(timescale), ...u32(actualDuration), 0x55,0xC4, 0,0])), box("hdlr", new Uint8Array([0,0,0,0, 0,0,0,0, ...sb("vide"), 0,0,0,0, 0,0,0,0, 0,0,0,0, ...sb("VideoHandler\0")])), minf);
    const tkhd = box("tkhd", new Uint8Array([0,0,0,15, 0,0,0,0, 0,0,0,0, ...u32(1), 0,0,0,0, ...u32(actualDuration), 0,0,0,0, 0,0,0,0, 0,0,0,0,0,0,0,0, 0,1,0,0,0,0,0,0,0,0,0,0, 0,0,0,0,0,1,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,0x40,0,0,0, ...u16(W),0,0, ...u16(H),0,0]));
    const mvhd = box("mvhd", new Uint8Array([0,0,0,0, 0,0,0,0, 0,0,0,0, ...u32(timescale), ...u32(actualDuration), 0,1,0,0, 1,0, 0,0, 0,0,0,0,0,0,0,0, 0,1,0,0,0,0,0,0,0,0,0,0, 0,0,0,0,0,1,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,0x40,0,0,0, 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0, ...u32(2)]));
    const moov = box("moov", mvhd, box("trak", tkhd, mdia));
    return new Blob([ftyp, mdat, moov], { type: "video/mp4" });
  }

  class VideoProcessor {
    constructor() {
      this.videoElement = document.createElement('video');
      this.videoElement.playsInline = true;
      this.videoElement.muted = true;
      this.videoElement.preload = 'auto';
      // Only set crossOrigin for http/https URLs, not blob: URLs on file://
      this.originalBlob = null;
      this.isTrimmed = false;
      this.maxWidth = 1920;
      this.maxHeight = 1080;
    }

    async loadVideo(fileOrBlob) {
      this.originalBlob = fileOrBlob;
      this.isTrimmed = false;
      return new Promise((resolve, reject) => {
        if (this.videoElement.src) {
          URL.revokeObjectURL(this.videoElement.src);
        }
        const videoURL = URL.createObjectURL(fileOrBlob);
        this.videoElement.src = videoURL;
        this.videoElement.load();

        let canplayTimer = null;
        let metaTimer = null;
        let resolved = false;

        const timeout = setTimeout(() => {
          if (!resolved) reject(new Error('视频加载超时，请检查文件格式'));
        }, 30000);

        const cleanup = () => {
          clearTimeout(timeout);
          clearTimeout(canplayTimer);
          clearTimeout(metaTimer);
          this.videoElement.oncanplaythrough = null;
          this.videoElement.oncanplay = null;
          this.videoElement.onloadedmetadata = null;
          this.videoElement.onerror = null;
        };

        const doResolve = () => {
          if (resolved) return;
          resolved = true;
          cleanup();
          resolve(this.videoElement);
        };

        this.videoElement.oncanplaythrough = doResolve;
        this.videoElement.oncanplay = () => {
          canplayTimer = setTimeout(() => {
            if (this.videoElement.readyState >= 2) doResolve();
          }, 1200);
        };
        this.videoElement.onloadedmetadata = () => {
          metaTimer = setTimeout(() => {
            doResolve();
          }, 3000);
        };
        this.videoElement.onerror = () => {
          cleanup();
          reject(new Error('视频格式暂不支持浏览器解码，请使用 H.264 MP4/WebM 视频或直接上传自定义封面'));
        };
      });
    }

    _getTargetDimensions(srcWidth, srcHeight) {
      let width = srcWidth || 720;
      let height = srcHeight || 720;
      if (width > this.maxWidth || height > this.maxHeight) {
        const ratio = Math.min(this.maxWidth / width, this.maxHeight / height);
        width = Math.round(width * ratio);
        height = Math.round(height * ratio);
      }
      width = width % 2 === 0 ? width : width - 1;
      height = height % 2 === 0 ? height : height - 1;
      return { width: Math.max(2, width), height: Math.max(2, height) };
    }

    async extractCoverFrame(timeInSeconds = 0) {
      if (!this.videoElement.src) {
        throw new Error('尚未加载视频');
      }
      return new Promise((resolve, reject) => {
        const targetTime = Math.max(0, Math.min(timeInSeconds, Math.max(0, (this.videoElement.duration || 1) - 0.05)));
        const capture = () => {
          try {
            const { width, height } = this._getTargetDimensions(
              this.videoElement.videoWidth,
              this.videoElement.videoHeight
            );
            const canvas = document.createElement('canvas');
            canvas.width = width;
            canvas.height = height;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(this.videoElement, 0, 0, width, height);
            canvas.toBlob(
              (blob) => {
                if (blob) resolve(blob);
                else reject(new Error('生成封面 Blob 失败'));
              },
              'image/jpeg',
              0.95
            );
          } catch (err) {
            reject(err);
          }
        };

        if (Math.abs(this.videoElement.currentTime - targetTime) < 0.03 && this.videoElement.readyState >= 2) {
          capture();
        } else {
          const onSeeked = () => {
            this.videoElement.removeEventListener('seeked', onSeeked);
            capture();
          };
          this.videoElement.addEventListener('seeked', onSeeked, { once: true });
          this.videoElement.currentTime = targetTime;
        }
      });
    }

    async extractFrames(startTime = 0, endTime = 3, fps = 24, onProgress = null) {
      const duration = Math.max(0.2, endTime - startTime);
      const totalFrames = Math.max(2, Math.min(120, Math.floor(duration * fps)));
      const { width, height } = this._getTargetDimensions(
        this.videoElement.videoWidth,
        this.videoElement.videoHeight
      );
      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      const frames = [];

      for (let i = 0; i < totalFrames; i++) {
        const t = startTime + (i / totalFrames) * duration;
        await new Promise((resolve) => {
          const onSeeked = () => {
            this.videoElement.removeEventListener('seeked', onSeeked);
            resolve();
          };
          this.videoElement.addEventListener('seeked', onSeeked, { once: true });
          this.videoElement.currentTime = Math.min(t, Math.max(0, (this.videoElement.duration || endTime) - 0.02));
        });
        ctx.drawImage(this.videoElement, 0, 0, width, height);
        const bitmap = await createImageBitmap(canvas);
        frames.push({ imageData: bitmap, width, height, timestamp: t });
        if (onProgress) {
          onProgress(Math.round(((i + 1) / totalFrames) * 100));
        }
      }
      return frames;
    }

    static getSupportedMimeType() {
      const types = [
        'video/mp4;codecs=avc1,mp4a.40.2',
        'video/mp4;codecs=avc1',
        'video/mp4',
        'video/webm;codecs=h264,opus',
        'video/webm;codecs=vp9,opus',
        'video/webm',
      ];
      if (typeof MediaRecorder !== 'undefined') {
        for (const t of types) {
          if (MediaRecorder.isTypeSupported(t)) return t;
        }
      }
      return '';
    }

    async convertToMP4(videoFrames, totalDuration, preserveAudio = true) {
      if (!Array.isArray(videoFrames) || videoFrames.length === 0) {
        throw new Error('无效的视频帧序列');
      }
      const first = videoFrames[0];
      const canvas = document.createElement('canvas');
      canvas.width = first.width || 640;
      canvas.height = first.height || 640;
      const ctx = canvas.getContext('2d');

      const fps = Math.max(8, Math.round(videoFrames.length / Math.max(0.5, totalDuration)));
      const frameInterval = 1000 / fps;
      const videoStream = canvas.captureStream(fps);

      let audioTrack = null;
      if (preserveAudio && this.videoElement && this.videoElement.src) {
        try {
          const origStream = this.videoElement.captureStream
            ? this.videoElement.captureStream()
            : this.videoElement.mozCaptureStream
            ? this.videoElement.mozCaptureStream()
            : null;
          if (origStream) {
            const tracks = origStream.getAudioTracks();
            if (tracks && tracks.length > 0) {
              audioTrack = tracks[0].clone();
            }
          }
        } catch (e) {
          console.warn('捕获原视频音轨跳过:', e);
        }
      }

      const combinedStream = new MediaStream([videoStream.getVideoTracks()[0]]);
      if (audioTrack) combinedStream.addTrack(audioTrack);

      const mimeType = VideoProcessor.getSupportedMimeType();
      const recorder = new MediaRecorder(combinedStream, {
        ...(mimeType ? { mimeType } : {}),
        videoBitsPerSecond: 12000000,
      });

      const chunks = [];
      return new Promise(async (resolve, reject) => {
        recorder.ondataavailable = (e) => e.data && e.data.size > 0 && chunks.push(e.data);
        recorder.onstop = () => {
          if (audioTrack) audioTrack.stop();
          resolve(new Blob(chunks, { type: mimeType || 'video/mp4' }));
        };
        recorder.onerror = (e) => reject(new Error('视频流录制失败: ' + (e.error?.message || e.message || '未知错误')));

        const bitmaps = [];
        for (const item of videoFrames) {
          const raw = item.imageData || item;
          bitmaps.push(raw instanceof ImageBitmap ? raw : await createImageBitmap(raw));
        }

        recorder.start();
        if (audioTrack) {
          this.videoElement.muted = false;
          this.videoElement.volume = 0.01;
          this.videoElement.currentTime = videoFrames[0].timestamp || 0;
          this.videoElement.play().catch(() => {});
        }

        let idx = 0;
        let lastTime = 0;
        const step = (ts) => {
          if (idx >= bitmaps.length) {
            recorder.stop();
            if (this.videoElement) this.videoElement.pause();
            return;
          }
          if (!lastTime || ts - lastTime >= frameInterval) {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.drawImage(bitmaps[idx], 0, 0, canvas.width, canvas.height);
            idx++;
            lastTime = ts;
          }
          requestAnimationFrame(step);
        };
        requestAnimationFrame(step);
      });
    }

    async framesToLiveVideoBlob(frameCanvases, options = {}) {
      const {
        fps = 16,
        minDurationSec = 3.0,
        loopMode = 'pingpong',
        crossfadeSteps = 1,
        backdrop = '#FFFFFF',
      } = options;

      if (!Array.isArray(frameCanvases) || frameCanvases.length === 0) {
        throw new Error('宫格帧列表为空');
      }

      const w = frameCanvases[0].width % 2 === 0 ? frameCanvases[0].width : frameCanvases[0].width - 1;
      const h = frameCanvases[0].height % 2 === 0 ? frameCanvases[0].height : frameCanvases[0].height - 1;

      const opaqueCanvases = frameCanvases.map((srcCanvas) => {
        const c = document.createElement('canvas');
        c.width = w;
        c.height = h;
        const ctx = c.getContext('2d');
        ctx.fillStyle = backdrop || '#FFFFFF';
        ctx.fillRect(0, 0, w, h);
        ctx.drawImage(srcCanvas, 0, 0, w, h);
        return c;
      });

      let cycle = [...opaqueCanvases];
      if (loopMode === 'pingpong' && opaqueCanvases.length > 2) {
        for (let i = opaqueCanvases.length - 2; i >= 1; i--) {
          cycle.push(opaqueCanvases[i]);
        }
      }

      if (crossfadeSteps > 0 && cycle.length > 1) {
        const blendedCycle = [];
        for (let i = 0; i < cycle.length; i++) {
          const curr = cycle[i];
          const next = cycle[(i + 1) % cycle.length];
          blendedCycle.push(curr);
          for (let s = 1; s <= crossfadeSteps; s++) {
            const alpha = s / (crossfadeSteps + 1);
            const inter = document.createElement('canvas');
            inter.width = w;
            inter.height = h;
            const ictx = inter.getContext('2d');
            ictx.globalAlpha = 1.0;
            ictx.drawImage(curr, 0, 0);
            ictx.globalAlpha = alpha;
            ictx.drawImage(next, 0, 0);
            blendedCycle.push(inter);
          }
        }
        cycle = blendedCycle;
      }

      const targetFramesCount = Math.max(cycle.length, Math.round(fps * minDurationSec));
      const fullSequence = [];
      while (fullSequence.length < targetFramesCount) {
        for (const fc of cycle) {
          fullSequence.push({ imageData: fc, width: w, height: h, timestamp: 0 });
          if (fullSequence.length >= targetFramesCount) break;
        }
      }

      return encodeCanvasesToAvc1Mp4Blob(cycle, Math.max(3.0, minDurationSec || 3.0), backdrop);
    }

    cleanup() {
      if (this.videoElement && this.videoElement.src) {
        URL.revokeObjectURL(this.videoElement.src);
        this.videoElement.src = '';
      }
      this.originalBlob = null;
      this.isTrimmed = false;
    }
  }

  root.Banano2Live = root.Banano2Live || {};
  root.Banano2Live.VideoProcessor = VideoProcessor;
})(typeof window !== 'undefined' ? window : globalThis);
