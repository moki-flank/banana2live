/**
 * banano2live - 实况照片核心构建与二进制逆向验真模块
 * 借鉴并深度升级 W4J1e/Video2LivePhoto/script/core/livephoto-builder.js：
 *   1. Google Motion Photo (.jpg 单文件):
 *      注入同时兼容 Google Motion Photo v1 (MicroVideoOffset / MotionPhotoVideoOffset)
 *      与 v2 (Container:Directory) 的 Adobe XMP APP1 (0xFFE1) 元数据段，并在 JPEG EOI 后拼接 MP4 视频流。
 *      支持小米、OPPO、vivo、华为、三星、Google 相册、Windows 10/11 照片应用与群晖 Synology Photos。
 *   2. Apple Live Photo (.zip):
 *      打包同名配对的 .JPG 封面与 .MOV 视频流 + livephoto_manifest.json。
 *   3. inspectMotionPhoto(arrayBuffer):
 *      纯前端字节级验真与拆解器，直接从单张实况 .jpg 中解析 XMP 并无损提取内嵌 MP4 视频与静态封面。
 */
(function (root) {

  function u32(v) { return [(v >>> 24) & 255, (v >>> 16) & 255, (v >>> 8) & 255, v & 255]; }
  function r32(b, o) { return ((b[o] << 24) >>> 0) + (b[o+1] << 16) + (b[o+2] << 8) + b[o+3]; }
  function strBytes(s) { const a = []; for (let i = 0; i < s.length; i++) a.push(s.charCodeAt(i) & 255); return a; }
  function mp4Box(type, ...payloads) {
    let len = 8; for (const p of payloads) len += p.length;
    const out = new Uint8Array(len);
    out.set(u32(len), 0);
    for (let i = 0; i < 4; i++) out[4 + i] = type.charCodeAt(i);
    let off = 8; for (const p of payloads) { out.set(p, off); off += p.length; }
    return out;
  }
  function parseMp4Boxes(u8, start = 0, end = u8.length) {
    const list = []; let pos = start;
    while (pos + 8 <= end) {
      let sz = r32(u8, pos);
      const type = String.fromCharCode(u8[pos+4], u8[pos+5], u8[pos+6], u8[pos+7]);
      if (sz === 0) sz = end - pos;
      if (sz < 8 || pos + sz > end) break;
      list.push({ type, offset: pos, size: sz, data: u8.subarray(pos, pos + sz), body: u8.subarray(pos + 8, pos + sz) });
      pos += sz;
    }
    return list;
  }
  function shiftStcoInPlace(u8, delta) {
    if (delta === 0) return;
    const containers = new Set(["moov", "trak", "mdia", "minf", "stbl"]);
    (function walk(buf, s, e) {
      for (const b of parseMp4Boxes(buf, s, e)) {
        if (containers.has(b.type)) walk(buf, b.offset + 8, b.offset + b.size);
        else if (b.type === "stco") {
          const cnt = r32(buf, b.offset + 12);
          for (let i = 0; i < cnt; i++) {
            const p = b.offset + 16 + i * 4;
            buf.set(u32(r32(buf, p) + delta), p);
          }
        }
      }
    })(u8, 0, u8.length);
  }
  function convertMp4ToAppleLiveMov(videoData, contentId) {
    const mp4U8 = videoData instanceof Uint8Array ? videoData : new Uint8Array(videoData);
    const top = parseMp4Boxes(mp4U8);
    const moovBox = top.find(b => b.type === "moov");
    const mdatBox = top.find(b => b.type === "mdat");
    if (!moovBox || !mdatBox) return mp4U8;
    const cid = String(contentId || "E621E1F8-C36C-495A-93FC-0C247A3E6E5F").slice(0, 36).toUpperCase();
    const ftyp = mp4Box("ftyp", new Uint8Array([...strBytes("qt  "), ...u32(0x00000200), ...strBytes("qt  ")]));
    const metaSample = new Uint8Array([0, 0, 0, 9, 0, 0, 0, 1, 0xFF]);
    const newMdatOffset = ftyp.length;
    const delta = newMdatOffset - mdatBox.offset;
    const metaSampleOffset = newMdatOffset + mdatBox.size;
    const newMdat = new Uint8Array(mdatBox.size + metaSample.length);
    newMdat.set(mdatBox.data, 0);
    newMdat.set(metaSample, mdatBox.size);
    newMdat.set(u32(newMdat.length), 0);
    const moovCopy = new Uint8Array(moovBox.data);
    shiftStcoInPlace(moovCopy, delta);
    const moovChildren = parseMp4Boxes(moovCopy, 8, moovCopy.length).filter(b => b.type !== "meta");
    const mvhd = moovChildren.find(b => b.type === "mvhd");
    let timescale = 600, duration = 1800;
    if (mvhd && mvhd.body[0] === 0) {
      timescale = r32(mvhd.body, 12);
      duration = r32(mvhd.body, 16);
    }
    const metaHdlr = mp4Box("hdlr", new Uint8Array([0,0,0,0, 0,0,0,0, ...strBytes("mdta"), 0,0,0,0, 0,0,0,0, 0,0,0,0, 0]));
    const keysBox = mp4Box("keys", new Uint8Array([0,0,0,0, 0,0,0,2]), mp4Box("mdta", new Uint8Array(strBytes("com.apple.quicktime.content.identifier"))), mp4Box("mdta", new Uint8Array(strBytes("com.apple.quicktime.still-image-time"))));
    const ilst = mp4Box("ilst", mp4Box("\0\0\0\x01", mp4Box("data", new Uint8Array([0,0,0,1, 0,0,0,0]), new Uint8Array(strBytes(cid)))), mp4Box("\0\0\0\x02", mp4Box("data", new Uint8Array([0,0,0,0x15, 0,0,0,0, 0xFF]))));
    const metaBox = mp4Box("meta", metaHdlr, keysBox, ilst);
    const dinf = mp4Box("dinf", mp4Box("dref", new Uint8Array([0,0,0,0, 0,0,0,1]), mp4Box("url ", new Uint8Array([0,0,0,1]))));
    const mTkhd = mp4Box("tkhd", new Uint8Array([0,0,0,15, 0,0,0,0, 0,0,0,0, ...u32(99), 0,0,0,0, ...u32(duration), 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0, 0,1,0,0,0,0,0,0,0,0,0,0, 0,0,0,0,0,1,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,0x40,0,0,0, 0,0,0,0, 0,0,0,0]));
    const mMdhd = mp4Box("mdhd", new Uint8Array([0,0,0,0, 0,0,0,0, 0,0,0,0, ...u32(timescale), ...u32(duration), 0x55,0xC4, 0,0]));
    const mHdlr = mp4Box("hdlr", new Uint8Array([0,0,0,0, ...strBytes("mhlr"), ...strBytes("meta"), ...strBytes("appl"), 0,0,0,0, 0,0,0,0, ...strBytes("CoreMedia Metadata\0")]));
    const gmhd = mp4Box("gmhd", mp4Box("gmin", new Uint8Array([0,0,0,0, 0,0x40, 0x80,0, 0x80,0, 0x80,0, 0,0, 0,0])));
    const mebx = mp4Box("mebx", new Uint8Array([0,0,0,0, 0,0, 0,1]), mp4Box("keys", mp4Box("\0\0\0\x01", mp4Box("keyd", new Uint8Array([...strBytes("mdta"), ...strBytes("com.apple.quicktime.still-image-time")])), mp4Box("dtyp", new Uint8Array([...strBytes("mdta"), 0,0,0,0x15])))));
    const mStbl = mp4Box("stbl", mp4Box("stsd", new Uint8Array([0,0,0,0, 0,0,0,1]), mebx), mp4Box("stts", new Uint8Array([0,0,0,0, 0,0,0,1, ...u32(1), ...u32(duration)])), mp4Box("stsc", new Uint8Array([0,0,0,0, 0,0,0,1, ...u32(1), ...u32(1), ...u32(1)])), mp4Box("stsz", new Uint8Array([0,0,0,0, 0,0,0,9, 0,0,0,1])), mp4Box("stco", new Uint8Array([0,0,0,0, 0,0,0,1, ...u32(metaSampleOffset)])));
    const metaTrak = mp4Box("trak", mTkhd, mp4Box("mdia", mMdhd, mHdlr, mp4Box("minf", gmhd, dinf, mStbl)));
    const newMoov = mp4Box("moov", ...moovChildren.map(b => b.data), metaBox, metaTrak);
    const out = new Uint8Array(ftyp.length + newMdat.length + newMoov.length);
    out.set(ftyp, 0); out.set(newMdat, ftyp.length); out.set(newMoov, ftyp.length + newMdat.length);
    return out;
  }
  function buildUniversalExifApp1(width = 1080, height = 1080, contentId = "E621E1F8-C36C-495A-93FC-0C247A3E6E5F") {
    const cid = String(contentId || "E621E1F8-C36C-495A-93FC-0C247A3E6E5F").slice(0, 36).toUpperCase();
    const buf = new Uint8Array(1024);
    const dv = new DataView(buf.buffer);
    const writeStr = (off, s) => { for (let i = 0; i < s.length; i++) buf[off + i] = s.charCodeAt(i) & 255; return off + s.length; };
    writeStr(0, "MM"); dv.setUint16(2, 0x002A, false); dv.setUint32(4, 8, false);
    const ifd0Count = 7; dv.setUint16(8, ifd0Count, false);
    let eOff = 10, dataOff = 10 + ifd0Count * 12 + 4;
    const addEntry = (tag, type, count, valOrOff, isShort = false) => {
      dv.setUint16(eOff, tag, false); dv.setUint16(eOff + 2, type, false); dv.setUint32(eOff + 4, count, false);
      if (isShort) { dv.setUint16(eOff + 8, valOrOff, false); dv.setUint16(eOff + 10, 0, false); }
      else dv.setUint32(eOff + 8, valOrOff, false);
      eOff += 12;
    };
    const putAscii = (s) => {
      const start = dataOff; writeStr(dataOff, s + "\0"); dataOff += s.length + 1;
      if (dataOff & 1) dataOff++;
      return { off: start, len: s.length + 1 };
    };
    const makeStr = putAscii("Apple"), modelStr = putAscii("iPhone 16 Pro"), softStr = putAscii("18.1"), dateStr = putAscii("2026:10:28 12:00:00");
    const exifIfdOffset = dataOff;
    addEntry(0x010F, 2, makeStr.len, makeStr.off);
    addEntry(0x0110, 2, modelStr.len, modelStr.off);
    addEntry(0x0112, 3, 1, 1, true);
    addEntry(0x0131, 2, softStr.len, softStr.off);
    addEntry(0x0132, 2, dateStr.len, dateStr.off);
    addEntry(0x0213, 3, 1, 1, true);
    addEntry(0x8769, 4, 1, exifIfdOffset);
    dv.setUint32(eOff, 0, false);
    const exifCount = 7; dv.setUint16(exifIfdOffset, exifCount, false);
    eOff = exifIfdOffset + 2; dataOff = exifIfdOffset + 2 + exifCount * 12 + 4;
    const mnStart = dataOff;
    writeStr(mnStart, "Apple iOS\0\0\x01MM");
    dv.setUint16(mnStart + 14, 2, false);
    dv.setUint16(mnStart + 16, 0x0011, false); dv.setUint16(mnStart + 18, 2, false); dv.setUint32(mnStart + 20, 37, false); dv.setUint32(mnStart + 24, 44, false);
    dv.setUint16(mnStart + 28, 0x0017, false); dv.setUint16(mnStart + 30, 4, false); dv.setUint32(mnStart + 32, 1, false); dv.setUint32(mnStart + 36, 0, false);
    dv.setUint32(mnStart + 40, 0, false);
    writeStr(mnStart + 44, cid + "\0");
    const mnLen = 44 + 37; dataOff = mnStart + mnLen; if (dataOff & 1) dataOff++;
    const ucStart = dataOff; const ucStr = "ASCII\0\0\0oplus_8388608";
    writeStr(ucStart, ucStr); const ucLen = ucStr.length; dataOff = ucStart + ucLen; if (dataOff & 1) dataOff++;
    addEntry(0x9000, 7, 4, 0x30323332);
    addEntry(0x9003, 2, dateStr.len, dateStr.off);
    addEntry(0x927C, 7, mnLen, mnStart);
    addEntry(0x9286, 7, ucLen, ucStart);
    addEntry(0xA001, 3, 1, 1, true);
    addEntry(0xA002, 4, 1, width);
    addEntry(0xA003, 4, 1, height);
    dv.setUint32(eOff, 0, false);
    const tiffBytes = buf.subarray(0, dataOff);
    const segLen = 2 + 6 + tiffBytes.length;
    const app1 = new Uint8Array(2 + segLen);
    app1[0] = 0xFF; app1[1] = 0xE1; app1[2] = (segLen >>> 8) & 255; app1[3] = segLen & 255;
    app1.set([0x45, 0x78, 0x69, 0x66, 0, 0], 4);
    app1.set(tiffBytes, 10);
    return app1;
  }

  class LivePhotoBuilder {
    constructor(videoProcessor) {
      this.coverImage = null;
      this.videoFrames = [];
      this.frameDuration = 0;
      this.videoProcessor = videoProcessor || null;
      this.directVideoBlob = null;
    }

    setCoverImage(blob) {
      this.coverImage = blob;
    }

    setDirectVideoBlob(blob) {
      this.directVideoBlob = blob;
    }

    setVideoFrames(frames, duration) {
      this.videoFrames = frames;
      this.frameDuration = duration;
    }

    async ensureJpegArrayBuffer(blobOrBuffer, backdrop = '#FFFFFF') {
      if (blobOrBuffer instanceof ArrayBuffer) {
        const u8 = new Uint8Array(blobOrBuffer);
        if (u8.length > 4 && u8[0] === 0xFF && u8[1] === 0xD8) {
          return blobOrBuffer;
        }
        blobOrBuffer = new Blob([blobOrBuffer]);
      }
      if (blobOrBuffer instanceof Blob && blobOrBuffer.type === 'image/jpeg') {
        const ab = await blobOrBuffer.arrayBuffer();
        const u8 = new Uint8Array(ab);
        if (u8.length > 4 && u8[0] === 0xFF && u8[1] === 0xD8) {
          return ab;
        }
      }
      // 使用 Canvas 将 PNG/WebP/DataURL 转换为高质量 JPEG
      const img = await LivePhotoBuilder.loadImageFromBlob(blobOrBuffer);
      const canvas = document.createElement('canvas');
      canvas.width = img.naturalWidth || img.width || 1024;
      canvas.height = img.naturalHeight || img.height || 1024;
      const ctx = canvas.getContext('2d');
      ctx.fillStyle = backdrop || '#FFFFFF';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0);
      const jpegBlob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.95));
      return await jpegBlob.arrayBuffer();
    }

    static loadImageFromBlob(blobOrUrl) {
      return new Promise((resolve, reject) => {
        const img = new Image();
        if (typeof blobOrUrl === 'string' && /^https?:\/\//i.test(blobOrUrl)) img.crossOrigin = 'anonymous';
        const url = typeof blobOrUrl === 'string' ? blobOrUrl : URL.createObjectURL(blobOrUrl);
        img.onload = () => {
          if (typeof blobOrUrl !== 'string') URL.revokeObjectURL(url);
          resolve(img);
        };
        img.onerror = (e) => {
          if (typeof blobOrUrl !== 'string') URL.revokeObjectURL(url);
          reject(new Error('封面图像加载失败'));
        };
        img.src = url;
      });
    }

    async build(format = 'both', baseName = 'banano2live', backdrop = '#FFFFFF') {
      if (!this.coverImage) {
        throw new Error('请先设置实况照片封面图');
      }

      const coverArrayBuffer = await this.ensureJpegArrayBuffer(this.coverImage, backdrop);
      let videoBlob = this.directVideoBlob;

      if (!videoBlob && this.videoProcessor) {
        if (this.videoProcessor.originalBlob && !this.videoProcessor.isTrimmed) {
          videoBlob = this.videoProcessor.originalBlob;
        } else if (Array.isArray(this.videoFrames) && this.videoFrames.length > 0) {
          videoBlob = await this.videoProcessor.convertToMP4(this.videoFrames, this.frameDuration);
        }
      }

      if (!videoBlob || !videoBlob.size) {
        throw new Error('未找到有效的实况视频流数据');
      }

      const videoArrayBuffer = await videoBlob.arrayBuffer();
      const timestamp = Date.now();
      const cleanPrefix = `${baseName}_${timestamp}`;

      const motionJpgBlob = this.createMotionPhoto(coverArrayBuffer, videoArrayBuffer);
      const coverJpgBlob = new Blob([coverArrayBuffer], { type: 'image/jpeg' });
      const mp4Blob = new Blob([videoArrayBuffer], { type: 'video/mp4' });

      let appleZipBlob = null;
      if (format === 'apple' || format === 'both') {
        try {
          appleZipBlob = await this._createAppleLivePhoto(coverArrayBuffer, videoArrayBuffer, cleanPrefix);
        } catch (e) {
          console.warn('Apple ZIP 打包跳过:', e);
        }
      }

      const inspection = LivePhotoBuilder.inspectMotionPhoto(await motionJpgBlob.arrayBuffer());

      return {
        type: format,
        blob: format === 'apple' && appleZipBlob ? appleZipBlob : motionJpgBlob,
        fileName: format === 'apple' && appleZipBlob ? `${cleanPrefix}.zip` : `${cleanPrefix}.jpg`,
        motionJpgBlob,
        motionJpgFileName: `${cleanPrefix}_live.jpg`,
        appleZipBlob,
        appleZipFileName: `${cleanPrefix}_apple_live.zip`,
        coverJpgBlob,
        coverJpgFileName: `${cleanPrefix}_cover.jpg`,
        videoMp4Blob: mp4Blob,
        videoMp4FileName: `${cleanPrefix}_video.mp4`,
        inspection,
      };
    }

    createMotionPhoto(coverData, videoData, presentationTimestampUs = 1500000) {
      const coverUint8 = new Uint8Array(coverData);
      const videoSize = videoData.byteLength;

      // 同时包含 Google Motion Photo v1 (MicroVideoOffset / MotionPhotoVideoOffset) 与 v2 (Container:Directory)
      const xmpContent =
        '<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>\n' +
        '<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Adobe XMP Core 5.1.0-jc003">\n' +
        '  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n' +
        '    <rdf:Description rdf:about=""\n' +
        '      xmlns:GCamera="http://ns.google.com/photos/1.0/camera/"\n' +
        '      xmlns:OpCamera="http://ns.oplus.com/photos/1.0/camera/"\n' +
        '      xmlns:MiCamera="http://ns.xiaomi.com/photos/1.0/camera/"\n' +
        '      xmlns:VCamera="http://ns.vivo.com/photos/1.0/camera/"\n' +
        '      OpCamera:MotionPhotoOwner="oplus"\n' +
        '      OpCamera:OLivePhotoVersion="2"\n' +
        '      OpCamera:MotionPhotoFeatureFlag="1"\n' +
        '      OpCamera:MotionPhotoPrimaryPresentationTimestampUs="' + presentationTimestampUs + '"\n' +
        '      OpCamera:VideoLength="' + videoSize + '"\n' +
        '      MiCamera:MicroVideo="1"\n' +
        '      MiCamera:MicroVideoOffset="' + videoSize + '"\n' +
        '      VCamera:LivePhoto="1"\n' +
        '      xmlns:Container="http://ns.google.com/photos/1.0/container/"\n' +
        '      xmlns:Item="http://ns.google.com/photos/1.0/container/item/"\n' +
        '      GCamera:MotionPhoto="1"\n' +
        '      GCamera:MotionPhotoVersion="1"\n' +
        '      GCamera:MotionPhotoPresentationTimestampUs="' + presentationTimestampUs + '"\n' +
        '      GCamera:MicroVideo="1"\n' +
        '      GCamera:MicroVideoVersion="1"\n' +
        '      GCamera:MicroVideoOffset="' + videoSize + '"\n' +
        '      GCamera:MotionPhotoVideoOffset="' + videoSize + '"\n' +
        '      GCamera:MicroVideoPresentationTimestampUs="' + presentationTimestampUs + '">\n' +
        '      <Container:Directory>\n' +
        '        <rdf:Seq>\n' +
        '          <rdf:li rdf:parseType="Resource">\n' +
        '            <Container:Item\n' +
        '              Item:Mime="image/jpeg"\n' +
        '              Item:Semantic="Primary"\n' +
        '              Item:Length="0"\n' +
        '              Item:Padding="0"/>\n' +
        '          </rdf:li>\n' +
        '          <rdf:li rdf:parseType="Resource">\n' +
        '            <Container:Item\n' +
        '              Item:Mime="video/mp4"\n' +
        '              Item:Semantic="MotionPhoto"\n' +
        '              Item:Length="' + videoSize + '"\n' +
        '              Item:Padding="0"/>\n' +
        '          </rdf:li>\n' +
        '        </rdf:Seq>\n' +
        '      </Container:Directory>\n' +
        '    </rdf:Description>\n' +
        '  </rdf:RDF>\n' +
        '</x:xmpmeta>\n' +
        '<?xpacket end="w"?>';

      const xmpNamespace = 'http://ns.adobe.com/xap/1.0/\x00';
      const xmpData = new TextEncoder().encode(xmpNamespace + xmpContent);

      const app1Segment = new Uint8Array(xmpData.byteLength + 4);
      const app1View = new DataView(app1Segment.buffer);
      app1View.setUint16(0, 0xFFE1);
      app1View.setUint16(2, xmpData.byteLength + 2);
      app1Segment.set(xmpData, 4);

      let insertPos = 2;
      if (coverUint8.length > 6 && coverUint8[2] === 0xFF && coverUint8[3] === 0xE0) {
        const app0Len = (coverUint8[4] << 8) | coverUint8[5];
        if (4 + app0Len <= coverUint8.length) {
          insertPos = 4 + app0Len;
        }
      }

      const exifSegment = buildUniversalExifApp1(1080, 1080, this._generateUUID());
      return new Blob(
        [
          coverUint8.slice(0, insertPos),
          exifSegment,
          app1Segment,
          coverUint8.slice(insertPos),
          videoData,
        ],
        { type: 'image/jpeg' }
      );
    }

    _generateUUID() {
      return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        const r = (Math.random() * 16) | 0;
        const v = c === 'x' ? r : (r & 0x3) | 0x8;
        return v.toString(16);
      }).toUpperCase();
    }

    async _createAppleLivePhoto(coverData, videoData, baseName = 'livephoto') {
      if (typeof JSZip === 'undefined') {
        throw new Error('未加载 JSZip 库，无法生成 Apple 格式压缩包');
      }
      const zip = new JSZip();
      const assetId = this._generateUUID();
      const coverU8 = new Uint8Array(coverData);
      const exifSeg = buildUniversalExifApp1(1080, 1080, assetId);
      let insPos = 2;
      if (coverU8.length > 6 && coverU8[2] === 0xFF && coverU8[3] === 0xE0) {
        const a0 = (coverU8[4] << 8) | coverU8[5];
        if (4 + a0 <= coverU8.length) insPos = 4 + a0;
      }
      const appleJpg = new Uint8Array(coverU8.length + exifSeg.length);
      appleJpg.set(coverU8.subarray(0, insPos), 0);
      appleJpg.set(exifSeg, insPos);
      appleJpg.set(coverU8.subarray(insPos), insPos + exifSeg.length);
      const appleMov = convertMp4ToAppleLiveMov(videoData, assetId);
      zip.file(`${baseName}.JPG`, appleJpg);
      zip.file(`${baseName}.MOV`, appleMov);
      zip.file(
        'livephoto_manifest.json',
        JSON.stringify(
          {
            schema: 'banano2live.apple-live-photo.v1',
            contentIdentifier: assetId,
            files: { cover: `${baseName}.JPG`, video: `${baseName}.MOV` },
            coverSizeBytes: coverData.byteLength,
            videoSizeBytes: videoData.byteLength,
          },
          null,
          2
        )
      );
      return await zip.generateAsync({ type: 'blob' });
    }

    static inspectMotionPhoto(arrayBuffer) {
      const u8 = new Uint8Array(arrayBuffer);
      const totalBytes = u8.length;
      if (totalBytes < 16 || u8[0] !== 0xFF || u8[1] !== 0xD8) {
        return { valid: false, reason: '非有效的 JPEG 图像文件 (缺少 0xFFD8 SOI 签名)', totalBytes };
      }

      const headerLen = Math.min(totalBytes, 65536);
      const headerStr = new TextDecoder('utf-8', { fatal: false }).decode(u8.slice(0, headerLen));
      const hasXmp = headerStr.includes('GCamera:MotionPhoto') || headerStr.includes('GCamera:MicroVideo');

      let videoSize = 0;
      const m1 = headerStr.match(/GCamera:MotionPhotoVideoOffset="(\d+)"/);
      const m2 = headerStr.match(/GCamera:MicroVideoOffset="(\d+)"/);
      const m3 = headerStr.match(/Item:Semantic="MotionPhoto"[^>]*Item:Length="(\d+)"/);
      if (m1) videoSize = parseInt(m1[1], 10);
      else if (m2) videoSize = parseInt(m2[1], 10);
      else if (m3) videoSize = parseInt(m3[1], 10);

      let splitPos = videoSize > 0 && videoSize < totalBytes ? totalBytes - videoSize : -1;

      const checkBoxSignature = (pos) => {
        if (pos <= 0 || pos + 8 > totalBytes) return '';
        return String.fromCharCode(u8[pos + 4], u8[pos + 5], u8[pos + 6], u8[pos + 7]);
      };

      let sig = checkBoxSignature(splitPos);
      // 兼容 WebM (EBML 0x1A 0x45 0xDF 0xA3) 或 MP4 (ftyp)
      let isWebm = splitPos > 0 && u8[splitPos] === 0x1A && u8[splitPos + 1] === 0x45 && u8[splitPos + 2] === 0xDF && u8[splitPos + 3] === 0xA3;

      if (sig !== 'ftyp' && !isWebm) {
        // 扫描 ftyp
        for (let i = 4; i < totalBytes - 8; i++) {
          if (u8[i] === 0x66 && u8[i + 1] === 0x74 && u8[i + 2] === 0x79 && u8[i + 3] === 0x70) {
            splitPos = i - 4;
            videoSize = totalBytes - splitPos;
            sig = 'ftyp';
            break;
          }
        }
      }

      const hasVideoStream = sig === 'ftyp' || isWebm || (hasXmp && splitPos > 0);
      const coverBlob = splitPos > 0 ? new Blob([u8.slice(0, splitPos)], { type: 'image/jpeg' }) : null;
      const videoBlob = splitPos > 0 ? new Blob([u8.slice(splitPos)], { type: isWebm ? 'video/webm' : 'video/mp4' }) : null;

      return {
        valid: Boolean(hasXmp && hasVideoStream),
        hasXmp,
        hasVideoStream,
        containerSignature: isWebm ? 'EBML/WebM' : sig || 'unknown',
        totalBytes,
        coverBytes: splitPos > 0 ? splitPos : totalBytes,
        videoBytes: splitPos > 0 ? videoSize : 0,
        splitPosition: splitPos,
        coverBlob,
        videoBlob,
      };
    }
  }

  root.Banano2Live = root.Banano2Live || {};
  root.Banano2Live.LivePhotoBuilder = LivePhotoBuilder;
})(typeof window !== 'undefined' ? window : globalThis);
