/**
 * banano2live - 纯前端宫格自适应切帧、外边缘 BFS 抠图与动作网格提取器
 */
(function (root) {
  function removeBackgroundBFS(canvas, bgThreshold = 240, colorDist = 28) {
    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;
    const imgData = ctx.getImageData(0, 0, w, h);
    const data = imgData.data;

    const corners = [[0, 0], [w - 1, 0], [0, h - 1], [w - 1, h - 1]];
    let avgR = 0, avgG = 0, avgB = 0;
    for (const [cx, cy] of corners) {
      const idx = (cy * w + cx) * 4;
      avgR += data[idx]; avgG += data[idx + 1]; avgB += data[idx + 2];
    }
    avgR /= 4; avgG /= 4; avgB /= 4;

    const visited = new Uint8Array(w * h);
    const queue = new Int32Array(w * h);
    let head = 0, tail = 0;

    function isBg(r, g, b) {
      const dr = r - avgR, dg = g - avgG, db = b - avgB;
      const dist = Math.sqrt(dr * dr + dg * dg + db * db);
      return dist < colorDist || (r > bgThreshold && g > bgThreshold && b > bgThreshold);
    }

    for (let x = 0; x < w; x++) {
      const idxTop = x * 4;
      if (isBg(data[idxTop], data[idxTop + 1], data[idxTop + 2])) { visited[x] = 1; queue[tail++] = x; }
      const btmPos = (h - 1) * w + x;
      const idxBtm = btmPos * 4;
      if (isBg(data[idxBtm], data[idxBtm + 1], data[idxBtm + 2])) { visited[btmPos] = 1; queue[tail++] = btmPos; }
    }
    for (let y = 0; y < h; y++) {
      const lPos = y * w;
      const idxL = lPos * 4;
      if (!visited[lPos] && isBg(data[idxL], data[idxL + 1], data[idxL + 2])) { visited[lPos] = 1; queue[tail++] = lPos; }
      const rPos = y * w + (w - 1);
      const idxR = rPos * 4;
      if (!visited[rPos] && isBg(data[idxR], data[idxR + 1], data[idxR + 2])) { visited[rPos] = 1; queue[tail++] = rPos; }
    }

    while (head < tail) {
      const pos = queue[head++];
      const px = pos % w;
      const py = (pos / w) | 0;
      const neighbors = [
        px > 0 ? pos - 1 : -1,
        px < w - 1 ? pos + 1 : -1,
        py > 0 ? pos - w : -1,
        py < h - 1 ? pos + w : -1,
      ];
      for (const n of neighbors) {
        if (n !== -1 && !visited[n]) {
          const nIdx = n * 4;
          if (isBg(data[nIdx], data[nIdx + 1], data[nIdx + 2])) {
            visited[n] = 1;
            queue[tail++] = n;
          }
        }
      }
    }

    for (let i = 0; i < w * h; i++) {
      if (visited[i]) data[i * 4 + 3] = 0;
    }
    ctx.putImageData(imgData, 0, 0);
    return canvas;
  }

  function sliceGridCanvas(img, gridLayout = '3x3', transparent = false, backdrop = '#FFFFFF') {
    const w = img.naturalWidth || img.width;
    const h = img.naturalHeight || img.height;
    const is16 = String(gridLayout).includes('4') || String(gridLayout) === '16';
    const rows = is16 ? 4 : 3;
    const cols = is16 ? 4 : 3;

    const stepX = w / cols;
    const stepY = h / rows;
    let cropSize = Math.round(Math.min(stepX, stepY) * 0.9375);
    if (cropSize % 2 !== 0) cropSize -= 1;
    const cropHalf = Math.round(cropSize / 2);

    const canvases = [];
    const dataUrls = [];

    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const cx = stepX * (c + 0.5);
        const cy = stepY * (r + 0.5);
        const sx = Math.max(0, Math.min(w - cropSize, Math.round(cx - cropHalf)));
        const sy = Math.max(0, Math.min(h - cropSize, Math.round(cy - cropHalf)));

        const rawCanvas = document.createElement('canvas');
        rawCanvas.width = cropSize;
        rawCanvas.height = cropSize;
        const rawCtx = rawCanvas.getContext('2d');
        rawCtx.drawImage(img, sx, sy, cropSize, cropSize, 0, 0, cropSize, cropSize);

        if (transparent) {
          removeBackgroundBFS(rawCanvas);
        }

        const finalCanvas = document.createElement('canvas');
        finalCanvas.width = cropSize;
        finalCanvas.height = cropSize;
        const fCtx = finalCanvas.getContext('2d');
        if (backdrop && backdrop !== 'transparent') {
          fCtx.fillStyle = backdrop;
          fCtx.fillRect(0, 0, cropSize, cropSize);
        }
        fCtx.drawImage(rawCanvas, 0, 0);

        canvases.push(finalCanvas);
        dataUrls.push(finalCanvas.toDataURL('image/png'));
      }
    }

    return { canvases, dataUrls, rows, cols, cropSize };
  }

  async function createMotionGuideDataUrl(file, gridLayout = '3x3') {
    const is16 = String(gridLayout).includes('4') || String(gridLayout) === '16';
    const rows = is16 ? 4 : 3;
    const cols = is16 ? 4 : 3;
    const total = rows * cols;
    const cellSize = 320;
    const border = 4;

    const sheet = document.createElement('canvas');
    sheet.width = cols * cellSize + (cols - 1) * border;
    sheet.height = rows * cellSize + (rows - 1) * border;
    const sctx = sheet.getContext('2d');
    sctx.fillStyle = '#FFFFFF';
    sctx.fillRect(0, 0, sheet.width, sheet.height);

    if (file.type.startsWith('video/') || /\.(mp4|mov|webm)$/i.test(file.name)) {
      const video = document.createElement('video');
      video.muted = true;
      video.playsInline = true;
      const url = URL.createObjectURL(file);
      video.src = url;
      await new Promise((res, rej) => {
        video.onloadeddata = res;
        video.onerror = () => rej(new Error('无法读取动作源视频'));
      });
      const dur = Math.max(0.5, video.duration || 2.0);
      for (let i = 0; i < total; i++) {
        const t = (i / Math.max(1, total - 1)) * (dur * 0.92);
        await new Promise((res) => {
          video.onseeked = res;
          video.currentTime = t;
        });
        const r = Math.floor(i / cols);
        const c = i % cols;
        const vw = video.videoWidth || 320;
        const vh = video.videoHeight || 320;
        const minD = Math.min(vw, vh);
        const sx = (vw - minD) / 2;
        const sy = (vh - minD) / 2;
        sctx.drawImage(video, sx, sy, minD, minD, c * (cellSize + border), r * (cellSize + border), cellSize, cellSize);
      }
      URL.revokeObjectURL(url);
      return sheet.toDataURL('image/jpeg', 0.92);
    } else {
      const dataUrl = await new Promise((res) => {
        const reader = new FileReader();
        reader.onload = (e) => res(e.target.result);
        reader.readAsDataURL(file);
      });
      const img = await new Promise((res, rej) => {
        const im = new Image();
        im.onload = () => res(im);
        im.onerror = rej;
        im.src = dataUrl;
      });
      for (let i = 0; i < total; i++) {
        const r = Math.floor(i / cols);
        const c = i % cols;
        sctx.drawImage(img, 0, 0, img.width, img.height, c * (cellSize + border), r * (cellSize + border), cellSize, cellSize);
      }
      return sheet.toDataURL('image/jpeg', 0.92);
    }
  }

  root.Banano2Live = root.Banano2Live || {};
  root.Banano2Live.removeBackgroundBFS = removeBackgroundBFS;
  root.Banano2Live.sliceGridCanvas = sliceGridCanvas;
  root.Banano2Live.createMotionGuideDataUrl = createMotionGuideDataUrl;
})(typeof window !== 'undefined' ? window : globalThis);
