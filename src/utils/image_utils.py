"""纯标准库的图片尺寸读取工具 (不依赖 Pillow)。

仅解析文件头部字节, 支持 APP_CONFIG.support_image_format 中的六种格式:
    png / gif / bmp / jpg(jpeg) / webp

无法识别或文件损坏时返回 None, 调用方按"未知尺寸"兜底处理。
"""

import struct


def _bmp_size(head: bytes) -> tuple[int, int] | None:
    """解析 BMP 文件头 (BITMAPINFOHEADER 或 OS/2 的 BITMAPCOREHEADER)。"""
    dib_size = struct.unpack("<I", head[14:18])[0]
    if dib_size == 12:  # BITMAPCOREHEADER: 宽高各为 2 字节无符号数
        width, height = struct.unpack("<HH", head[18:22])
    else:  # BITMAPINFOHEADER 及更高版本: 宽高各为 4 字节有符号数
        width, height = struct.unpack("<ii", head[18:26])

    # 高度为负表示自上而下存储的位图, 取绝对值
    if width <= 0 or height == 0:
        return None
    return width, abs(height)


# JPEG 帧头 (SOF) 段标记, 携带图像宽高
_JPEG_SOF_MARKERS = {
    0xC0,
    0xC1,
    0xC2,
    0xC3,
    0xC5,
    0xC6,
    0xC7,
    0xC9,
    0xCA,
    0xCB,
    0xCD,
    0xCE,
    0xCF,
}


def _jpeg_size(fh) -> tuple[int, int] | None:
    """顺序扫描 JPEG 段, 在 SOF 段读取宽高 (SOS/EOI 之后不再有 SOF)。"""
    if fh.read(2) != b"\xff\xd8":
        return None

    while True:
        # 段标记: 0xFF 开头, 连续的 0xFF 为填充字节
        first = fh.read(1)
        if not first:
            return None
        if first != b"\xff":
            return None
        second = fh.read(1)
        while second == b"\xff":
            second = fh.read(1)
        if not second:
            return None
        marker = second[0]

        # 无载荷段: SOI / EOI / RSTn / TEM
        if marker == 0xD9 or marker == 0xDA or marker == 0x01 or 0xD0 <= marker <= 0xD7:
            return None

        seg_len = fh.read(2)
        if len(seg_len) < 2:
            return None
        length = struct.unpack(">H", seg_len)[0]
        if length < 2:
            return None
        payload = fh.read(length - 2)
        if len(payload) < length - 2:
            return None

        if marker in _JPEG_SOF_MARKERS:
            if len(payload) < 5:
                return None
            # SOF 载荷: 精度(1) 高度(2) 宽度(2) ...
            height, width = struct.unpack(">HH", payload[1:5])
            return width, height


def _webp_size(head: bytes) -> tuple[int, int] | None:
    """解析 WebP 的 VP8X / VP8 (有损) / VP8L (无损) 三种块头。"""
    fmt = head[12:16]
    if fmt == b"VP8X":
        # 扩展格式: 24 bit 宽-1 + 24 bit 高-1
        width = 1 + (head[24] | head[25] << 8 | head[26] << 16)
        height = 1 + (head[27] | head[28] << 8 | head[29] << 16)
        return width, height
    if fmt == b"VP8 ":
        # 有损: 帧头 3 字节 (关键帧固定为 9D 01 2A) 后跟 3 字节宽高 (各 14 bit)
        if head[20:23] != b"\x9d\x01\x2a":
            return None
        bits = head[23] | head[24] << 8 | head[25] << 16
        return bits & 0x3FFF, (bits >> 14) & 0x3FFF
    if fmt == b"VP8L":
        # 无损: 1 字节签名 0x2F + 4 字节载荷 (宽-1 14bit, 高-1 14bit)
        if head[20] != 0x2F:
            return None
        bits = head[21] | head[22] << 8 | head[23] << 16 | head[24] << 24
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    return None


def get_image_size(image_path) -> tuple[int, int] | None:
    """读取图片像素宽高 (width, height), 无法识别时返回 None。

    Args:
        image_path: 图片文件路径 (str / PathLike)
    Returns:
        (width, height) 或 None
    """
    try:
        with open(image_path, "rb") as fh:
            head = fh.read(32)

            if len(head) >= 24 and head.startswith(b"\x89PNG\r\n\x1a\n"):
                if head[12:16] != b"IHDR":
                    return None
                return struct.unpack(">II", head[16:24])

            if len(head) >= 10 and head[:6] in (b"GIF87a", b"GIF89a"):
                return struct.unpack("<HH", head[6:10])

            if len(head) >= 26 and head.startswith(b"BM"):
                return _bmp_size(head)

            if len(head) >= 30 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
                return _webp_size(head)

            if head.startswith(b"\xff\xd8"):
                fh.seek(0)
                return _jpeg_size(fh)
    except OSError:
        pass

    return None
