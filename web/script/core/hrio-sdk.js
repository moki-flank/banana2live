/**
 * banano2live - 浏览器端 HrioAPI 多模态 SDK 封装 (含模型契约自适应参数规范化 + 跨域媒体无损拉取桥)
 * 同时支持：
 *   1. 视频直生接口 (/v1/videos + 异步任务状态轮询 /v1/videos/{task_id} + 模型参数自动对齐)
 *   2. 图像宫格生成接口 (/v1/images/generations)
 *   3. 跨域媒体无损拉取 (fetchRemoteMediaBlob: 支持本地 8095 代理流、JSONP <script> 零跨域桥、HrioDesktop 桥)
 */
(function (root) {
  // 全局 JSONP 回调池 (用于 file:// 协议下绕过 CORS 与 PNA 限制无损拉取远程 MP4/JPG 二进制)
  const proxyCallbacks = {};
  root.__B2L_PROXY_RESOLVE = function (reqId, payload) {
    const cb = proxyCallbacks[reqId];
    if (cb) {
      delete proxyCallbacks[reqId];
      cb(payload);
    }
  };

  function base64ToBlob(b64, mime = 'application/octet-stream') {
    const clean = String(b64 || '').replace(/\s+/g, '');
    const byteChars = atob(clean);
    const bytes = new Uint8Array(byteChars.length);
    for (let i = 0; i < byteChars.length; i++) {
      bytes[i] = byteChars.charCodeAt(i);
    }
    return new Blob([bytes], { type: mime });
  }

  const LIVE_VIDEO_PRESETS = {
    breeze_portrait: {
      title: '🍃 微风拂发',
      desc: 'soft breeze gently blowing through hair and clothes, natural eye blink and warm subtle smile',
      motion: 'Camera remains steady in a portrait framing; a gentle breeze softly lifts strands of hair and fabric edges, the subject blinks naturally and forms a warm, vivid smile with soft sunlight bokeh shimmering in the background.',
      audio: 'soft gentle wind breeze and quiet natural ambient atmosphere',
    },
    turn_smile: {
      title: '✨ 回眸一笑',
      desc: 'gently turning head toward the camera, eyes sparkling and breaking into a sweet smile',
      motion: 'Starting from a poised angle, the subject smoothly turns their head slightly toward the lens, eyes catching the light with a natural blink, followed by a radiant, authentic smile.',
      audio: 'subtle rustle of clothing and warm outdoor ambient sound',
    },
    wink_heart: {
      title: '😉 眨眼比心',
      desc: 'playful wink at the camera while making a cute finger heart gesture',
      motion: 'The subject looks directly into the camera, raises a hand to form a cute finger heart near the cheek, gives a playful wink with one eye, and smiles sweetly.',
      audio: 'light cheerful ambiance',
    },
    cafe_steam: {
      title: '☕ 咖啡热气',
      desc: 'holding a warm cup of coffee with delicate steam rising, soft window light',
      motion: 'Delicate wisps of warm steam curl upward from the cup, the subject takes a gentle breath, eyes softening with a relaxed smile as golden afternoon light shifts subtly.',
      audio: 'quiet cozy cafe background murmur and soft ceramic clink',
    },
    pet_tilt: {
      title: '🐶 萌宠歪头',
      desc: 'adorable pet blinking big round eyes, twitching ears, and tilting head curiously',
      motion: 'The cute pet looks straight at the lens, ears perking up and twitching softly, then tilts its head curiously to the side while blinking its bright eyes.',
      audio: 'soft adorable pet breathing and gentle collar bell chime',
    },
    cyber_rain: {
      title: '🌧️ 霓虹雨夜',
      desc: 'cyberpunk neon reflections shimmering on wet glass, raindrops trickling down',
      motion: 'Vibrant neon reflections pulse and shimmer across rain-slicked surfaces, droplets trickle down the foreground, and cinematic volumetric mist drifts slowly.',
      audio: 'gentle rain pattering and distant atmospheric city hum',
    },
    ocean_sunset: {
      title: '🌊 海浪微澜',
      desc: 'golden sunset waves lapping gently at the shore, hair swaying in sea breeze',
      motion: 'Sparkling golden-hour ocean waves roll gently onto the shore in the background, sea breeze softly sways the subject hair, creating a dreamy live photo moment.',
      audio: 'soothing ocean waves washing ashore and coastal breeze',
    },
  };

  const ACTION_PRESETS = {
    waving: { title: '👋 挥手问好', desc: 'gently waving hand and smiling warmly' },
    breeze: { title: '🍃 微风呼吸', desc: 'gentle wind blowing hair and clothes with natural blinking' },
    wink: { title: '😉 俏皮眨眼', desc: 'playfully winking one eye and tilting head slightly' },
    heart: { title: '🫶 比心发射', desc: 'making a cute heart gesture with hands and smiling sweetly' },
    laughing: { title: '😆 开心大笑', desc: 'laughing happily with shoulders bouncing gently' },
    crying: { title: '😭 委屈哭泣', desc: 'sadly crying with teardrops and wiping eyes' },
  };

  function buildVideoLivePrompt(subject, presetKey, style, hasFirstRef, hasLastRef) {
    const preset = LIVE_VIDEO_PRESETS[presetKey];
    const motion = preset
      ? preset.motion
      : 'Subtle, lifelike continuous Live Photo motion: ' + subject + '. Natural breathing, gentle hair and fabric movement, expressive eye blink, and soft ambient light shifts.';
    const audio = preset ? preset.audio : 'natural subtle ambient sound matching the scene';
    let refText = '';
    if (hasFirstRef && hasLastRef) {
      refText = 'FIRST-TO-LAST FRAME LIVE PHOTO TRANSITION: Start seamlessly from the exact composition of the first reference image and transition smoothly into the final reference image. ';
    } else if (hasFirstRef) {
      refText = 'IMAGE-TO-LIVE-PHOTO CONSISTENCY: Start from the exact composition, lighting, and character identity of the reference image. Preserve facial features and outfit strictly while bringing the moment to life. ';
    }
    return 'High-resolution Live Photo moment: ' + subject + '. ' + refText + 'MOTION & CAMERA: Steady portrait framing with zero jarring cuts. ' + motion + ' AUDIO: ' + audio + '. NEGATIVE CONSTRAINTS: No text, no subtitles, no watermarks, no sudden cuts. STYLE: ' + style + '.';
  }

  function buildGridLivePrompt(subject, presetKey, gridLayout, style, hasRef, is4k) {
    const is16 = String(gridLayout).includes('4') || String(gridLayout) === '16';
    const count = is16 ? 16 : 9;
    const gridName = is16 ? '4x4' : '3x3';
    const preset = ACTION_PRESETS[presetKey] || LIVE_VIDEO_PRESETS[presetKey];
    const actDesc = preset ? subject + ', ' + preset.desc : subject;
    const refLock = hasRef
      ? 'REFERENCE CHARACTER LOCK: Maintain exact, strict identity consistency with the character in the provided reference image across all panels. '
      : '';
    const resTag = is4k ? ', ultra high resolution 4K UHD, 4096x4096 resolution, extremely sharp fine details, masterpiece' : '';
    return (
      'A clean ' + gridName + ' animation contact sheet sprite grid consisting of exactly ' + count + ' equal square panels showing ONE continuous, ultra-smooth Live Photo micro-motion cycle: ' +
      refLock + actDesc + '. ' +
      'CRITICAL MOTION RULES: 1. LOCKED CAMERA: Absolutely static camera, identical distance and zoom, consistent background. ' +
      '2. SEQUENTIAL PROGRESSIVE MICRO-MOTION FLOW from Panel 1 to Panel ' + count + ', returning smoothly to Panel 1 posture for a seamless loop. ' +
      'LAYOUT: Equal ' + gridName + ' grid separated by thin, clean, solid white borders. ' +
      'STRICT NEGATIVE CONSTRAINT: ABSOLUTELY NO numbers, NO digits, NO frame index watermark, NO text, NO logos anywhere in the image. ' +
      'STYLE: ' + style + resTag + '.'
    );
  }

  function buildMotionTransferPrompt(actionHint, gridLayout, style, is4k) {
    const is16 = String(gridLayout).includes('4') || String(gridLayout) === '16';
    const count = is16 ? 16 : 9;
    const gridName = is16 ? '4x4' : '3x3';
    const resTag = is4k ? ', ultra high resolution 4K UHD, 4096x4096, masterpiece' : '';
    return (
      'A clean ' + gridName + ' animation contact sheet grid consisting of exactly ' + count + ' sequential square panels. ' +
      'DUAL REFERENCE MOTION TRANSFER TASK: ' +
      '1. TARGET CHARACTER REFERENCE (Image 1): Strictly preserve the exact appearance, face, hair, costume, and art style of the character in Image 1. ' +
      '2. MOTION & POSE SEQUENCE GUIDE (Image 2): Mirror and transfer the exact progressive posture, hand gestures, and facial expression shifts from Image 2 onto the character from Image 1 cell by cell across all ' + count + ' panels (' + actionHint + '). ' +
      'LOCKED CAMERA, equal ' + gridName + ' grid separated by thin solid white borders, ABSOLUTELY NO numbers or digits. STYLE: ' + style + resTag + '.'
    );
  }

  class HrioWebClient {
    constructor(apiKey, baseUrl = 'https://hrioapi.hrio.site/v1') {
      this.apiKey = (apiKey || '').trim();
      this.baseUrl = (baseUrl || 'https://hrioapi.hrio.site/v1').replace(/\/+$/, '');
    }

    ensureAuth() {
      if (!this.apiKey && !(window.hrioBridge && typeof window.hrioBridge.sdkGenerate === 'function')) {
        throw new Error('请先在顶部输入您的 HrioAPI Key (sk-xxxx)，或使用「本地视频 / 本地宫格图」零安装离线模式！');
      }
    }

    /**
     * 根据不同视频大模型的上游契约规范化请求参数，彻底避免：
     *   - veo-3-1 only supports duration=8
     *   - model veo-3.1-fast-generate-preview does not support video resolution 1k
     */
    static normalizeVideoModelPayload(model, prompt, { aspectRatio = '9:16', duration = 8, resolution = '', generateAudio = true, images = [] }) {
      const mLower = String(model || '').trim().toLowerCase();
      let effDuration = Number(duration) || 8;
      let effAr = aspectRatio || '9:16';
      let effRes = resolution || '';
      let includeSeconds = true;
      let includeAudio = true;

      if (mLower.includes('veo-')) {
        // Veo 3.0 / 3.1 上游仅支持 8 秒时长
        effDuration = 8;
        if (!['16:9', '9:16'].includes(effAr)) {
          effAr = '9:16';
        }
        if (mLower.includes('veo-3.1')) {
          // veo-3.1 仅支持 720p / 1080p / 4K，不支持 1K
          if (!['720p', '1080p', '4K'].includes(effRes)) {
            effRes = '720p';
          }
        } else {
          // veo-3.0 不传非标分辨率
          effRes = '';
        }
      } else if (mLower.includes('seedance')) {
        effDuration = Math.max(4, Math.min(15, effDuration === 5 ? 6 : effDuration));
        effRes = '720p';
        includeSeconds = false;
        includeAudio = false;
        if (mLower.includes('doubao-seedance-2-0')) {
          effAr = '16:9';
        }
      } else if (mLower.includes('sora') || mLower.includes('grok-imagine-video')) {
        effDuration = 8;
        effRes = '';
      } else if (mLower.includes('minimax')) {
        effDuration = Math.max(4, Math.min(15, effDuration));
        effRes = '720p';
      }

      const payload = {
        model,
        prompt,
        aspect_ratio: effAr,
        duration: effDuration,
        async: true,
      };
      if (includeSeconds) payload.seconds = effDuration;
      if (includeAudio) payload.generate_audio = Boolean(generateAudio);
      if (effRes) payload.resolution = effRes;

      if (images && images.length > 0) {
        payload.image = images[0];
        payload.image_url = images[0];
        payload.first_image_url = images[0];
        payload.images = images;
        payload.image_urls = images;
        if (images.length >= 2) {
          payload.last_image_url = images[1];
          payload.extra_images = images.slice(1);
          payload.Ingredients_images = images;
        }
      }

      return payload;
    }

    /**
     * 跨源媒体二进制无损获取器 (解决 img2.hrio.site 在 file:// 或非同源下的 CORS 拦截)：
     *   1. Data URL / Blob URL 直接转换；
     *   2. HrioDesktop 宿主桥 (assets.importRemote + assets.readBase64)；
     *   3. 本地 banano2live 代理服务 (http://127.0.0.1:8095/api/proxy?url=...)；
     *   4. 本地 JSONP <script> 二进制桥 (http://127.0.0.1:8095/api/proxy_js?url=...，100% 免疫 file:// CORS 与 PNA)；
     *   5. 浏览器原生 fetch。
     */
    static async fetchRemoteMediaBlob(url, defaultMime = 'video/mp4', options = {}) {
      const targetDur = options && options.duration != null ? Number(options.duration) : 0;
      const durQuery = targetDur > 0 ? '&duration=' + encodeURIComponent(targetDur) : '';
      if (!url) throw new Error('媒体 URL 为空');
      if (url instanceof Blob) return url;
      const uStr = String(url).trim();

      if (uStr.startsWith('data:')) {
        const parts = uStr.split(',');
        const mimeMatch = parts[0].match(/data:([^;]+)/);
        return base64ToBlob(parts[1], mimeMatch ? mimeMatch[1] : defaultMime);
      }
      if (uStr.startsWith('blob:')) {
        const r = await fetch(uStr);
        return await r.blob();
      }

      // 通道 1: Hrio Desktop Bridge
      try {
        const br =
          (window.hrioDesktop && typeof window.hrioDesktop.invoke === 'function' && window.hrioDesktop) ||
          (window.parent && window.parent !== window && window.parent.hrioDesktop) ||
          (window.top && window.top !== window && window.top.hrioDesktop);
        if (br && typeof br.invoke === 'function') {
          const ext = defaultMime.includes('video') ? 'mp4' : 'jpg';
          const rec = await br.invoke('assets.importRemote', { url: uStr, name: 'b2l_media.' + ext, mime: defaultMime });
          const aid = rec && (rec.id || rec.assetId);
          if (aid) {
            const pay = await br.invoke('assets.readBase64', { assetId: aid });
            if (pay && pay.base64) {
              return base64ToBlob(pay.base64, pay.mime || defaultMime);
            }
          }
        }
      } catch (_e) {}

      // 通道 2: 本地 127.0.0.1:8095/8096/8090 /api/proxy 二进制流代理
      const proxyBases = HrioWebClient.getProxyBases();

      for (const base of proxyBases) {
        try {
          const pResp = await fetch(base + '/api/proxy?url=' + encodeURIComponent(uStr) + durQuery, { mode: 'cors' });
          if (pResp.ok) {
            const blob = await pResp.blob();
            if (blob && blob.size > 0) return blob;
          }
        } catch (_e) {}
      }

      // 通道 3: 本地 127.0.0.1:8095/api/proxy_js JSONP <script> 桥 (彻底无视 file:// 下的 CORS 与 PNA 预检拦截)
      for (const base of proxyBases) {
        try {
          const blob = await new Promise((resolve, reject) => {
            const reqId = 'req_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8);
            const script = document.createElement('script');
            const timer = setTimeout(() => {
              delete proxyCallbacks[reqId];
              script.remove();
              reject(new Error('proxy_js timeout'));
            }, 45000);

            proxyCallbacks[reqId] = (res) => {
              clearTimeout(timer);
              script.remove();
              if (res && res.ok && res.b64) {
                resolve(base64ToBlob(res.b64, res.mime || defaultMime));
              } else {
                reject(new Error((res && res.error) || 'proxy_js failed'));
              }
            };
            script.onerror = () => {
              clearTimeout(timer);
              delete proxyCallbacks[reqId];
              script.remove();
              reject(new Error('proxy_js network error'));
            };
            script.src = base + '/api/proxy_js?url=' + encodeURIComponent(uStr) + durQuery + '&id=' + encodeURIComponent(reqId);
            document.head.appendChild(script);
          });
          if (blob && blob.size > 0) return blob;
        } catch (_e) {}
      }

      // 通道 4: 原生直接 fetch
      const directResp = await fetch(uStr, { mode: 'cors', credentials: 'omit' });
      if (!directResp.ok) {
        throw new Error('拉取媒体失败 (HTTP ' + directResp.status + ')');
      }
      return await directResp.blob();
    }

    static getProxyBases() {
      const proxyBases = [];
      if (typeof window !== 'undefined' && window.location && window.location.protocol.startsWith('http') && window.location.origin !== 'null') {
        proxyBases.push(window.location.origin);
      }
      for (const b of ['http://127.0.0.1:8095', 'http://127.0.0.1:8096', 'http://127.0.0.1:8090']) {
        if (!proxyBases.includes(b)) proxyBases.push(b);
      }
      return proxyBases;
    }

    async requestApi(subpath, { method = 'POST', body = null } = {}) {
      const cleanSub = String(subpath || '').replace(/^\/+/, '');
      for (const proxyBase of HrioWebClient.getProxyBases()) {
        try {
          const headers = { 'X-Target-Base-Url': this.baseUrl };
          if (body !== null) headers['Content-Type'] = 'application/json';
          if (this.apiKey) headers['Authorization'] = 'Bearer ' + this.apiKey;
          const resp = await fetch(proxyBase + '/api/v1/' + cleanSub, {
            method,
            mode: 'cors',
            headers,
            body: body !== null ? JSON.stringify(body) : undefined,
          });
          return resp;
        } catch (_e) {}
      }
      const headers = {};
      if (body !== null) headers['Content-Type'] = 'application/json';
      if (this.apiKey) headers['Authorization'] = 'Bearer ' + this.apiKey;
      return await fetch(this.baseUrl + '/' + cleanSub, {
        method,
        headers,
        body: body !== null ? JSON.stringify(body) : undefined,
      });
    }

    async generateImage({ model = 'gemini-nano-banana-2.1', prompt, images = [], size = '1024x1024' }) {
      this.ensureAuth();
      if (!this.apiKey && window.hrioBridge && typeof window.hrioBridge.sdkGenerate === 'function') {
        const res = await window.hrioBridge.sdkGenerate({
          title: 'banano2live 宫格动作序列生成',
          kind: 'image',
          model,
          prompt,
          parameters: { size, ...(images.length ? { images } : {}) },
        });
        const inner = res?.response || res;
        const first = inner?.data?.[0] || inner?.images?.[0] || {};
        if (first.b64_json) return 'data:image/png;base64,' + first.b64_json;
        if (first.url || inner?.url || inner?.image_url) return first.url || inner.url || inner.image_url;
      }

      const payload = { model, prompt, n: 1, size };
      if (images && images.length > 0) {
        payload.images = images;
        payload.media = images.map((url) => ({ kind: 'image', url }));
      }

      const resp = await this.requestApi('images/generations', { method: 'POST', body: payload });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(data?.error?.message || data?.message || 'HTTP ' + resp.status);
      }
      const first = data?.data?.[0] || data?.images?.[0] || {};
      if (first.data_url) return first.data_url;
      if (first.b64_json) {
        return 'data:image/png;base64,' + first.b64_json;
      }
      const url = first.url || data.url || data.image_url || data.output_url;
      if (!url) throw new Error('未能从生图响应中解析到图片数据');
      return url;
    }

    static extractVideoUrl(obj) {
      if (!obj || typeof obj !== 'object') return null;
      const direct =
        obj.video_url ||
        obj.url ||
        obj.output_url ||
        obj?.output?.[0]?.url ||
        obj?.result?.video_url ||
        obj?.result?.url ||
        obj?.data?.[0]?.url ||
        obj?.data?.video_url ||
        obj?.data?.url ||
        obj?.response?.generatedVideos?.[0]?.video?.uri ||
        obj?.response?.generateVideoResponse?.[0]?.video?.uri;
      if (typeof direct === 'string' && /^https?:\/\//i.test(direct)) return direct;
      if (typeof obj.output === 'string' && /^https?:\/\//i.test(obj.output)) return obj.output;
      return null;
    }

    static extractTaskId(obj) {
      if (!obj || typeof obj !== 'object') return null;
      return obj.task_id || obj.id || obj?.data?.task_id || obj?.data?.id || obj.name || obj.operation_name || null;
    }

    async generateVideo({
      model = 'veo-3.0-fast-generate-001',
      prompt,
      images = [],
      aspectRatio = '9:16',
      duration = 8,
      resolution = '',
      generateAudio = true,
      onProgress = null,
    }) {
      this.ensureAuth();

      const payload = HrioWebClient.normalizeVideoModelPayload(model, prompt, {
        aspectRatio,
        duration,
        resolution,
        generateAudio,
        images,
      });

      if (!this.apiKey && window.hrioBridge && typeof window.hrioBridge.sdkGenerate === 'function') {
        if (onProgress) onProgress('submitted', 10);
        const bridgeRes = await window.hrioBridge.sdkGenerate({
          title: 'banano2live 实况视频生成',
          kind: 'video',
          model,
          prompt,
          parameters: payload,
        });
        const vUrl = HrioWebClient.extractVideoUrl(bridgeRes?.response || bridgeRes);
        if (vUrl) return vUrl;
      }

      if (onProgress) onProgress('submitted', 5);

      const resp = await this.requestApi('videos', { method: 'POST', body: payload });
      const initData = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(initData?.error?.message || initData?.message || '视频请求失败 (HTTP ' + resp.status + ')');
      }

      const directUrl = HrioWebClient.extractVideoUrl(initData);
      if (directUrl) {
        if (onProgress) onProgress('completed', 100);
        return directUrl;
      }

      const taskId = HrioWebClient.extractTaskId(initData);
      if (!taskId) {
        throw new Error('视频接口未返回有效的视频链接或 task_id');
      }

      const statusUrl = this.baseUrl + '/videos/' + encodeURIComponent(taskId);
      const startTs = Date.now();
      const timeoutMs = 600000;

      while (Date.now() - startTs < timeoutMs) {
        await new Promise((r) => setTimeout(r, 3000));
        const pollResp = await this.requestApi('videos/' + encodeURIComponent(taskId), { method: 'GET' });
        const pollData = await pollResp.json().catch(() => ({}));
        const rawState = String(pollData.status || pollData.state || pollData.task_status || pollData?.data?.status || 'processing').toLowerCase();
        let pct = pollData.progress || pollData.progress_percent || pollData?.data?.progress || null;
        if (typeof pct === 'number' && pct > 0 && pct <= 1) pct = Math.round(pct * 100);
        if (onProgress) onProgress(rawState, pct);

        const readyUrl = HrioWebClient.extractVideoUrl(pollData);
        if (['completed', 'succeeded', 'success', 'done', 'finished'].includes(rawState) || readyUrl) {
          if (onProgress) onProgress('completed', 100);
          return readyUrl || statusUrl + '/content';
        }
        if (['failed', 'error', 'canceled', 'cancelled', 'expired', 'rejected'].includes(rawState)) {
          const detailErr =
            pollData?.result?.error?.message ||
            pollData?.error?.message ||
            pollData?.message ||
            JSON.stringify(pollData);
          throw new Error('视频生成任务失败 (' + rawState + '): ' + detailErr);
        }
      }
      throw new Error('视频生成任务轮询超时');
    }
  }

  root.Banano2Live = root.Banano2Live || {};
  root.Banano2Live.LIVE_VIDEO_PRESETS = LIVE_VIDEO_PRESETS;
  root.Banano2Live.ACTION_PRESETS = ACTION_PRESETS;
  root.Banano2Live.buildVideoLivePrompt = buildVideoLivePrompt;
  root.Banano2Live.buildGridLivePrompt = buildGridLivePrompt;
  root.Banano2Live.buildMotionTransferPrompt = buildMotionTransferPrompt;
  root.Banano2Live.HrioWebClient = HrioWebClient;
})(typeof window !== 'undefined' ? window : globalThis);
