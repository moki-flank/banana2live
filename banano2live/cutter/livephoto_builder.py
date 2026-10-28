# -*- coding: utf-8 -*-
"""
实况照片构建与逆向验真核心模块 (Live Photo Builder & Binary Inspector)
借鉴并深度增强 W4J1e/Video2LivePhoto：
  1. Google Motion Photo (.jpg 单文件动态照片)：
     - 同时注入 MotionPhoto v1 (GCamera:MicroVideoOffset / MotionPhotoVideoOffset)
       与 MotionPhoto v2 (Container:Directory Item:Semantic="MotionPhoto") 双规范 XMP 元数据；
     - 完美兼容小米 (HyperOS/MIUI)、OPPO/一加、vivo、华为/荣耀、三星、Google 相册、
       Windows 10/11 照片应用以及群晖 (Synology Photos)；
     - 完整保留原视频 H.264/HEVC 视频流与原声 AAC 音轨。
  2. Apple Live Photo (.zip 双文件配对归档)：
     - 生成同名配对的 .JPG 静态封面与 .MOV 实况视频流压缩包，支持 iOS/macOS/Windows/群晖导入。
  3. 字节级逆向验真与解包器 (inspect_motion_photo)：
     - 支持对任意生成的实况 .jpg 进行二进制检验，解析 XMP 偏移量并无损分离出封面 .jpg 与内嵌 .mp4 视频。
"""

import io
import os
import re
import uuid
import struct
import zipfile
import json
from typing import Union, Optional, Dict, Any
from PIL import Image

from .matting import composite_on_backdrop


def ensure_jpeg_bytes(
    cover_source: Union[str, bytes, Image.Image],
    backdrop: str = "#FFFFFF",
    quality: int = 95,
) -> bytes:
    """将任意路径、字节流或 PIL.Image 规范化为标准 JPEG 二进制流 (0xFFD8 ... 0xFFD9)"""
    if isinstance(cover_source, bytes):
        # 如果已经是标准 JPEG 且未混入尾部视频，直接返回；否则经 PIL 重新规范化
        if len(cover_source) > 4 and cover_source[:2] == b"\xff\xd8" and cover_source[-2:] == b"\xff\xd9":
            return cover_source
        im = Image.open(io.BytesIO(cover_source))
    elif isinstance(cover_source, str):
        if not os.path.isfile(cover_source):
            raise FileNotFoundError(f"未找到封面图文件: {cover_source}")
        with open(cover_source, "rb") as f:
            raw = f.read()
        if raw[:2] == b"\xff\xd8" and raw[-2:] == b"\xff\xd9" and b"MotionPhoto" not in raw[:8192]:
            return raw
        im = Image.open(io.BytesIO(raw))
    elif isinstance(cover_source, Image.Image):
        im = cover_source
    else:
        raise TypeError(f"不支持的封面数据类型: {type(cover_source)}")

    rgb = composite_on_backdrop(im, backdrop=backdrop)
    buf = io.BytesIO()
    rgb.save(buf, format="JPEG", quality=quality, subsampling=0)
    return buf.getvalue()


def ensure_video_bytes(video_source: Union[str, bytes]) -> bytes:
    """读取视频字节流"""
    if isinstance(video_source, bytes):
        if not video_source:
            raise ValueError("视频字节流为空")
        return video_source
    if isinstance(video_source, str):
        if not os.path.isfile(video_source):
            raise FileNotFoundError(f"未找到视频文件: {video_source}")
        with open(video_source, "rb") as f:
            data = f.read()
        if not data:
            raise ValueError(f"视频文件为空: {video_source}")
        return data
    raise TypeError(f"不支持的视频数据类型: {type(video_source)}")




def build_universal_exif_app1(width: int = 1080, height: int = 1080, content_id: str = "") -> bytes:
    """
    构建同时兼容 iOS Live Photo (MakerNote 0x0011 ContentIdentifier)
    与 Android (OPPO UserComment oplus_8388608 + 标准 ExifIFD) 的 EXIF APP1 段 (0xFFE1 Exif\0\0)
    """
    cid = (content_id or str(uuid.uuid4()).upper())[:36].upper()
    buf = bytearray(1024)
    def w_str(off: int, b: bytes):
        buf[off:off+len(b)] = b
        return off + len(b)

    w_str(0, b"MM")
    struct.pack_into(">HI", buf, 2, 0x002A, 8)
    ifd0_count = 7
    struct.pack_into(">H", buf, 8, ifd0_count)
    e_off = 10
    d_off = 10 + ifd0_count * 12 + 4

    def add_entry(tag: int, typ: int, cnt: int, val_or_off: int, is_short: bool = False):
        nonlocal e_off
        struct.pack_into(">HHI", buf, e_off, tag, typ, cnt)
        if is_short:
            struct.pack_into(">HH", buf, e_off + 8, val_or_off & 0xFFFF, 0)
        else:
            struct.pack_into(">I", buf, e_off + 8, val_or_off & 0xFFFFFFFF)
        e_off += 12

    def put_ascii(s: str):
        nonlocal d_off
        raw = s.encode("ascii") + b"\x00"
        start = d_off
        w_str(d_off, raw)
        d_off += len(raw)
        if d_off & 1:
            d_off += 1
        return start, len(raw)

    make_off, make_len = put_ascii("Apple")
    model_off, model_len = put_ascii("iPhone 16 Pro")
    soft_off, soft_len = put_ascii("18.1")
    date_off, date_len = put_ascii("2026:10:28 12:00:00")
    exif_ifd_off = d_off

    add_entry(0x010F, 2, make_len, make_off)
    add_entry(0x0110, 2, model_len, model_off)
    add_entry(0x0112, 3, 1, 1, True)
    add_entry(0x0131, 2, soft_len, soft_off)
    add_entry(0x0132, 2, date_len, date_off)
    add_entry(0x0213, 3, 1, 1, True)
    add_entry(0x8769, 4, 1, exif_ifd_off)
    struct.pack_into(">I", buf, e_off, 0)

    exif_count = 7
    struct.pack_into(">H", buf, exif_ifd_off, exif_count)
    e_off = exif_ifd_off + 2
    d_off = exif_ifd_off + 2 + exif_count * 12 + 4

    mn_start = d_off
    w_str(mn_start, b"Apple iOS\x00\x00\x01MM")
    struct.pack_into(">H", buf, mn_start + 14, 2)
    struct.pack_into(">HHII", buf, mn_start + 16, 0x0011, 2, 37, 44)
    struct.pack_into(">HHII", buf, mn_start + 28, 0x0017, 4, 1, 0)
    struct.pack_into(">I", buf, mn_start + 40, 0)
    w_str(mn_start + 44, cid.encode("ascii") + b"\x00")
    mn_len = 44 + 37
    d_off = mn_start + mn_len
    if d_off & 1:
        d_off += 1

    uc_start = d_off
    uc_bytes = b"ASCII\x00\x00\x00oplus_8388608"
    w_str(uc_start, uc_bytes)
    uc_len = len(uc_bytes)
    d_off = uc_start + uc_len
    if d_off & 1:
        d_off += 1

    add_entry(0x9000, 7, 4, 0x30323332)
    add_entry(0x9003, 2, date_len, date_off)
    add_entry(0x927C, 7, mn_len, mn_start)
    add_entry(0x9286, 7, uc_len, uc_start)
    add_entry(0xA001, 3, 1, 1, True)
    add_entry(0xA002, 4, 1, int(width))
    add_entry(0xA003, 4, 1, int(height))
    struct.pack_into(">I", buf, e_off, 0)

    tiff_payload = bytes(buf[:d_off])
    body = b"Exif\x00\x00" + tiff_payload
    return struct.pack(">HH", 0xFFE1, len(body) + 2) + body


def _mp4_box(btype: bytes, *payloads: bytes) -> bytes:
    body = b"".join(payloads)
    return struct.pack(">I", 8 + len(body)) + btype + body


def _parse_mp4_boxes(data: bytes, start: int = 0, end: Optional[int] = None):
    if end is None:
        end = len(data)
    out = []
    pos = start
    while pos + 8 <= end:
        sz = struct.unpack_from(">I", data, pos)[0]
        btype = data[pos+4:pos+8]
        if sz == 0:
            sz = end - pos
        if sz < 8 or pos + sz > end:
            break
        out.append((btype, pos, sz, data[pos:pos+sz], data[pos+8:pos+sz]))
        pos += sz
    return out


def _shift_stco_inplace(buf: bytearray, delta: int):
    if delta == 0:
        return
    containers = {b"moov", b"trak", b"mdia", b"minf", b"stbl"}
    def walk(s: int, e: int):
        for btype, off, sz, _, _ in _parse_mp4_boxes(buf, s, e):
            if btype in containers:
                walk(off + 8, off + sz)
            elif btype == b"stco":
                cnt = struct.unpack_from(">I", buf, off + 12)[0]
                for i in range(cnt):
                    p = off + 16 + i * 4
                    old_v = struct.unpack_from(">I", buf, p)[0]
                    struct.pack_into(">I", buf, p, (old_v + delta) & 0xFFFFFFFF)
    walk(0, len(buf))


def convert_mp4_to_apple_live_mov(mp4_bytes: bytes, content_id: str) -> bytes:
    cid = (content_id or str(uuid.uuid4()).upper())[:36].upper()
    top = _parse_mp4_boxes(mp4_bytes)
    moov_item = next((x for x in top if x[0] == b"moov"), None)
    mdat_item = next((x for x in top if x[0] == b"mdat"), None)
    if not moov_item or not mdat_item:
        return mp4_bytes

    ftyp = _mp4_box(b"ftyp", b"qt  ", struct.pack(">I", 0x00000200), b"qt  ")
    meta_sample = b"\x00\x00\x00\x09\x00\x00\x00\x01\xff"

    new_mdat_off = len(ftyp)
    delta = new_mdat_off - mdat_item[1]
    meta_sample_off = new_mdat_off + mdat_item[2]
    new_mdat = _mp4_box(b"mdat", mdat_item[4], meta_sample)

    moov_copy = bytearray(moov_item[3])
    _shift_stco_inplace(moov_copy, delta)
    moov_children = [x for x in _parse_mp4_boxes(bytes(moov_copy), 8, len(moov_copy)) if x[0] != b"meta"]
    mvhd_item = next((x for x in moov_children if x[0] == b"mvhd"), None)
    timescale, duration = 600, 1800
    if mvhd_item and mvhd_item[4][0] == 0:
        timescale, duration = struct.unpack_from(">II", mvhd_item[4], 12)

    meta_hdlr = _mp4_box(b"hdlr", b"\x00" * 8 + b"mdta" + b"\x00" * 13)
    k1 = _mp4_box(b"mdta", b"com.apple.quicktime.content.identifier")
    k2 = _mp4_box(b"mdta", b"com.apple.quicktime.still-image-time")
    keys_box = _mp4_box(b"keys", struct.pack(">II", 0, 2), k1, k2)
    item1 = _mp4_box(b"\x00\x00\x00\x01", _mp4_box(b"data", struct.pack(">II", 1, 0), cid.encode("ascii")))
    item2 = _mp4_box(b"\x00\x00\x00\x02", _mp4_box(b"data", struct.pack(">IIB", 0x15, 0, 0xFF)))
    meta_box = _mp4_box(b"meta", meta_hdlr, keys_box, _mp4_box(b"ilst", item1, item2))

    dinf = _mp4_box(b"dinf", _mp4_box(b"dref", struct.pack(">II", 0, 1), _mp4_box(b"url ", struct.pack(">I", 1))))
    m_tkhd = _mp4_box(b"tkhd", struct.pack(">IIIIII", 15, 0, 0, 99, 0, duration) + b"\x00" * 16 + struct.pack(">IIIIIIIII", 0x00010000, 0, 0, 0, 0x00010000, 0, 0, 0, 0x40000000) + b"\x00" * 8)
    m_mdhd = _mp4_box(b"mdhd", struct.pack(">IIII", 0, 0, 0, timescale) + struct.pack(">IHH", duration, 0x55C4, 0))
    m_hdlr = _mp4_box(b"hdlr", b"\x00\x00\x00\x00mhlrmetaappl" + b"\x00" * 8 + b"CoreMedia Metadata\x00")
    gmhd = _mp4_box(b"gmhd", _mp4_box(b"gmin", b"\x00\x00\x00\x00\x00\x40\x80\x00\x80\x00\x80\x00\x00\x00\x00\x00"))
    mebx_keys = _mp4_box(b"keys", _mp4_box(b"\x00\x00\x00\x01", _mp4_box(b"keyd", b"mdtacom.apple.quicktime.still-image-time"), _mp4_box(b"dtyp", b"mdta\x00\x00\x00\x15")))
    mebx = _mp4_box(b"mebx", b"\x00\x00\x00\x00\x00\x00\x00\x01", mebx_keys)
    m_stbl = _mp4_box(
        b"stbl",
        _mp4_box(b"stsd", struct.pack(">II", 0, 1), mebx),
        _mp4_box(b"stts", struct.pack(">IIII", 0, 1, 1, duration)),
        _mp4_box(b"stsc", struct.pack(">IIIII", 0, 1, 1, 1, 1)),
        _mp4_box(b"stsz", struct.pack(">III", 0, 9, 1)),
        _mp4_box(b"stco", struct.pack(">III", 0, 1, meta_sample_off)),
    )
    meta_trak = _mp4_box(b"trak", m_tkhd, _mp4_box(b"mdia", m_mdhd, m_hdlr, _mp4_box(b"minf", gmhd, dinf, m_stbl)))
    new_moov = _mp4_box(b"moov", *[x[3] for x in moov_children], meta_box, meta_trak)
    return ftyp + new_mdat + new_moov


def build_motion_photo_xmp(video_size: int, presentation_timestamp_us: int = 1500000) -> bytes:
    """
    构建同时兼容 Google Motion Photo v1 / v2、小米、群晖 Synology Photos 与 Windows 11 的 XMP 数据包
    """
    xmp_str = (
        '<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Adobe XMP Core 5.1.0-jc003">\n'
        '  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
        '    <rdf:Description rdf:about=""\n'
        '      xmlns:GCamera="http://ns.google.com/photos/1.0/camera/"\n'
        '      xmlns:OpCamera="http://ns.oplus.com/photos/1.0/camera/"\n'
        '      xmlns:MiCamera="http://ns.xiaomi.com/photos/1.0/camera/"\n'
        '      xmlns:VCamera="http://ns.vivo.com/photos/1.0/camera/"\n'
        '      OpCamera:MotionPhotoOwner="oplus"\n'
        '      OpCamera:OLivePhotoVersion="2"\n'
        '      OpCamera:MotionPhotoFeatureFlag="1"\n'
        f'      OpCamera:MotionPhotoPrimaryPresentationTimestampUs="{int(presentation_timestamp_us)}"\n'
        f'      OpCamera:VideoLength="{int(video_size)}"\n'
        '      MiCamera:MicroVideo="1"\n'
        f'      MiCamera:MicroVideoOffset="{int(video_size)}"\n'
        '      VCamera:LivePhoto="1"\n'
        '      xmlns:Container="http://ns.google.com/photos/1.0/container/"\n'
        '      xmlns:Item="http://ns.google.com/photos/1.0/container/item/"\n'
        '      GCamera:MotionPhoto="1"\n'
        '      GCamera:MotionPhotoVersion="1"\n'
        f'      GCamera:MotionPhotoPresentationTimestampUs="{int(presentation_timestamp_us)}"\n'
        '      GCamera:MicroVideo="1"\n'
        '      GCamera:MicroVideoVersion="1"\n'
        f'      GCamera:MicroVideoOffset="{int(video_size)}"\n'
        f'      GCamera:MotionPhotoVideoOffset="{int(video_size)}"\n'
        f'      GCamera:MicroVideoPresentationTimestampUs="{int(presentation_timestamp_us)}">\n'
        '      <Container:Directory>\n'
        '        <rdf:Seq>\n'
        '          <rdf:li rdf:parseType="Resource">\n'
        '            <Container:Item\n'
        '              Item:Mime="image/jpeg"\n'
        '              Item:Semantic="Primary"\n'
        '              Item:Length="0"\n'
        '              Item:Padding="0"/>\n'
        '          </rdf:li>\n'
        '          <rdf:li rdf:parseType="Resource">\n'
        '            <Container:Item\n'
        '              Item:Mime="video/mp4"\n'
        '              Item:Semantic="MotionPhoto"\n'
        f'              Item:Length="{int(video_size)}"\n'
        '              Item:Padding="0"/>\n'
        '          </rdf:li>\n'
        '        </rdf:Seq>\n'
        '      </Container:Directory>\n'
        '    </rdf:Description>\n'
        '  </rdf:RDF>\n'
        '</x:xmpmeta>\n'
        '<?xpacket end="w"?>'
    )
    namespace = b"http://ns.adobe.com/xap/1.0/\x00"
    xmp_payload = namespace + xmp_str.encode("utf-8")
    seg_length = len(xmp_payload) + 2
    app1_header = struct.pack(">HH", 0xFFE1, seg_length)
    return app1_header + xmp_payload


def build_google_motion_photo(
    cover_source: Union[str, bytes, Image.Image],
    video_source: Union[str, bytes],
    output_jpg_path: Optional[str] = None,
    presentation_timestamp_us: int = 1500000,
    backdrop: str = "#FFFFFF",
) -> bytes:
    """
    将封面图与视频流合成为单文件 Google Motion Photo (.jpg)。
    对齐 W4J1e/Video2LivePhoto 的 APP1 (0xFFE1) 注入策略并增强双规范兼容性。
    """
    cover_bytes = ensure_jpeg_bytes(cover_source, backdrop=backdrop)
    video_bytes = ensure_video_bytes(video_source)
    app1_segment = build_motion_photo_xmp(len(video_bytes), presentation_timestamp_us)

    # 寻找注入位置：如果紧跟 SOI (0xFFD8) 的是 APP0 (0xFFE0)，则插在 APP0 之后，否则插在 SOI 之后
    insert_pos = 2
    if len(cover_bytes) > 6 and cover_bytes[2] == 0xFF and cover_bytes[3] == 0xE0:
        app0_len = (cover_bytes[4] << 8) | cover_bytes[5]
        if 4 + app0_len <= len(cover_bytes):
            insert_pos = 4 + app0_len

    exif_segment = build_universal_exif_app1(1080, 1080, str(uuid.uuid4()).upper())
    motion_photo_bytes = (
        cover_bytes[:insert_pos]
        + exif_segment
        + app1_segment
        + cover_bytes[insert_pos:]
        + video_bytes
    )

    if output_jpg_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_jpg_path)), exist_ok=True)
        with open(output_jpg_path, "wb") as f:
            f.write(motion_photo_bytes)

    return motion_photo_bytes


def build_apple_livephoto_zip(
    cover_source: Union[str, bytes, Image.Image],
    video_source: Union[str, bytes],
    output_zip_path: str,
    base_name: str = "livephoto",
    backdrop: str = "#FFFFFF",
) -> str:
    """
    构建 Apple Live Photo 兼容压缩包 (.zip)，内含同名配对的 .jpg 与 .mov 文件，
    以及元数据清单文件，支持 iOS / macOS / Windows 照片应用与群晖相册。
    """
    cover_bytes = ensure_jpeg_bytes(cover_source, backdrop=backdrop)
    video_bytes = ensure_video_bytes(video_source)
    asset_id = str(uuid.uuid4()).upper()

    os.makedirs(os.path.dirname(os.path.abspath(output_zip_path)), exist_ok=True)
    clean_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", base_name).strip() or "livephoto"

    manifest = {
        "schema": "banano2live.apple-live-photo.v1",
        "contentIdentifier": asset_id,
        "files": {
            "cover": f"{clean_name}.jpg",
            "video": f"{clean_name}.mov",
        },
        "coverSizeBytes": len(cover_bytes),
        "videoSizeBytes": len(video_bytes),
    }

    with zipfile.ZipFile(output_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        exif_seg = build_universal_exif_app1(1080, 1080, asset_id)
        ins_p = 4 + ((cover_bytes[4] << 8) | cover_bytes[5]) if (len(cover_bytes) > 6 and cover_bytes[2] == 0xFF and cover_bytes[3] == 0xE0) else 2
        apple_jpg = cover_bytes[:ins_p] + exif_seg + cover_bytes[ins_p:]
        apple_mov = convert_mp4_to_apple_live_mov(video_bytes, asset_id)
        zf.writestr(f"{clean_name}.JPG", apple_jpg)
        zf.writestr(f"{clean_name}.MOV", apple_mov)
        zf.writestr("livephoto_manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))

    return output_zip_path


def inspect_motion_photo(
    jpg_path_or_bytes: Union[str, bytes],
    extract_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    字节级逆向解析与验真 Google Motion Photo (.jpg)：
    1. 验证 JPEG SOI (0xFFD8) 头；
    2. 扫描 APP1 XMP 元数据段，提取 GCamera:MotionPhoto / MicroVideoOffset / MotionPhotoVideoOffset；
    3. 精确定位内嵌 MP4 视频流的起始字节偏移并验证 ISO Base Media (ftyp) 签名；
    4. 若指定 extract_dir，则无损拆解还原出 cover.jpg 与 embedded_video.mp4。
    """
    if isinstance(jpg_path_or_bytes, str):
        if not os.path.isfile(jpg_path_or_bytes):
            raise FileNotFoundError(f"未找到实况图文件: {jpg_path_or_bytes}")
        with open(jpg_path_or_bytes, "rb") as f:
            data = f.read()
    else:
        data = jpg_path_or_bytes

    total_size = len(data)
    if total_size < 16 or data[:2] != b"\xff\xd8":
        return {"valid": False, "reason": "not_a_jpeg", "total_bytes": total_size}

    header_window = data[: min(total_size, 65536)].decode("utf-8", errors="ignore")
    has_xmp = "GCamera:MotionPhoto" in header_window or "GCamera:MicroVideo" in header_window

    offset_match = (
        re.search(r'GCamera:MotionPhotoVideoOffset="(\d+)"', header_window)
        or re.search(r'GCamera:MicroVideoOffset="(\d+)"', header_window)
        or re.search(r'Item:Semantic="MotionPhoto"[^>]*Item:Length="(\d+)"', header_window)
    )

    video_size = int(offset_match.group(1)) if offset_match else 0
    split_pos = total_size - video_size if (0 < video_size < total_size) else -1

    # 如果未通过偏移量找到，尝试在 JPEG EOI (0xFFD9) 后搜索 MP4 'ftyp' box
    if split_pos <= 0 or data[split_pos + 4 : split_pos + 8] != b"ftyp":
        ftyp_idx = data.find(b"ftyp", 2)
        if ftyp_idx > 4:
            split_pos = ftyp_idx - 4
            video_size = total_size - split_pos

    has_mp4_ftyp = (
        0 < split_pos < total_size - 8
        and data[split_pos + 4 : split_pos + 8] == b"ftyp"
    )

    result: Dict[str, Any] = {
        "valid": bool(has_xmp and has_mp4_ftyp),
        "has_xmp": has_xmp,
        "has_mp4_stream": has_mp4_ftyp,
        "total_bytes": total_size,
        "cover_bytes": split_pos if split_pos > 0 else total_size,
        "video_bytes": video_size if split_pos > 0 else 0,
        "video_offset_from_end": video_size,
        "split_position": split_pos,
    }

    if extract_dir and split_pos > 0 and has_mp4_ftyp:
        os.makedirs(extract_dir, exist_ok=True)
        cover_out = os.path.join(extract_dir, "extracted_cover.jpg")
        video_out = os.path.join(extract_dir, "extracted_video.mp4")
        with open(cover_out, "wb") as fc:
            fc.write(data[:split_pos])
        with open(video_out, "wb") as fv:
            fv.write(data[split_pos:])
        result["extracted_cover_path"] = cover_out
        result["extracted_video_path"] = video_out

    return result


def build_livephoto_bundle(
    cover_source: Union[str, bytes, Image.Image],
    video_source: Union[str, bytes],
    output_dir: str = "output",
    base_name: str = "livephoto",
    fmt: str = "both",
    presentation_timestamp_us: int = 1500000,
    backdrop: str = "#FFFFFF",
) -> Dict[str, Any]:
    """
    一站式导出完整实况图产物包：
      - Google Motion Photo 单文件动态图 (<base_name>_live.jpg)
      - Apple Live Photo 双文件配对包 (<base_name>_apple_live.zip)
      - 独立高清封面图 (<base_name>_cover.jpg)
      - 独立实况视频流 (<base_name>_video.mp4)
    并自动执行字节级验真 (inspect_motion_photo)。
    """
    os.makedirs(output_dir, exist_ok=True)
    clean_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", base_name).strip() or "livephoto"

    cover_bytes = ensure_jpeg_bytes(cover_source, backdrop=backdrop)
    video_bytes = ensure_video_bytes(video_source)

    cover_path = os.path.join(output_dir, f"{clean_name}_cover.jpg")
    video_path = os.path.join(output_dir, f"{clean_name}_video.mp4")
    with open(cover_path, "wb") as f:
        f.write(cover_bytes)
    with open(video_path, "wb") as f:
        f.write(video_bytes)

    motion_jpg_path: Optional[str] = None
    apple_zip_path: Optional[str] = None
    verification: Optional[Dict[str, Any]] = None

    fmt_lower = (fmt or "both").lower()
    if fmt_lower in ("both", "auto", "google", "jpg", "motion"):
        motion_jpg_path = os.path.join(output_dir, f"{clean_name}_live.jpg")
        mp_bytes = build_google_motion_photo(
            cover_bytes,
            video_bytes,
            output_jpg_path=motion_jpg_path,
            presentation_timestamp_us=presentation_timestamp_us,
            backdrop=backdrop,
        )
        verification = inspect_motion_photo(mp_bytes)

    if fmt_lower in ("both", "apple", "zip", "ios"):
        apple_zip_path = os.path.join(output_dir, f"{clean_name}_apple_live.zip")
        build_apple_livephoto_zip(
            cover_bytes,
            video_bytes,
            output_zip_path=apple_zip_path,
            base_name=clean_name,
            backdrop=backdrop,
        )

    return {
        "ok": True,
        "format": fmt_lower,
        "cover_jpg": cover_path,
        "video_mp4": video_path,
        "motion_photo_jpg": motion_jpg_path,
        "apple_live_zip": apple_zip_path,
        "verification": verification,
    }
