"""单元测试: src/utils/image_utils.py

被测对象:
    get_image_size    纯标准库的图片像素尺寸解析 (png/gif/bmp/jpg/webp)

说明:
    测试图片由字节流手工构造 (不依赖 Pillow 与真实样例):
    - PNG / GIF / BMP / WebP 只需头部若干字节即可解析宽高;
    - JPEG 构造 "SOI + SOF0 + EOI" 的最小段序列, 解析器只顺序扫描段标记,
      不校验熵编码数据, 因此该最小文件足以覆盖 SOF 解析路径。
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from utils.image_utils import get_image_size


# --------------------------------------------------------------------------- #
# 手工构造各格式的最小图片文件
# --------------------------------------------------------------------------- #
def _png(width: int, height: int) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x02\x00\x00\x00"
        + struct.pack(">I", 0)
    )


def _gif(width: int, height: int) -> bytes:
    return b"GIF89a" + struct.pack("<HH", width, height) + b"\x00" * 32


def _bmp(width: int, height: int) -> bytes:
    # BITMAPINFOHEADER (40 字节), 高度为负表示自上而下存储
    return (
        b"BM"
        + struct.pack("<IHHI", 54, 0, 0, 54)
        + struct.pack("<Iii", 40, width, height)
        + b"\x00" * 32
    )


def _webp_vp8x(width: int, height: int) -> bytes:
    def _24bit(value: int) -> bytes:
        return bytes([value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF])

    return (
        b"RIFF"
        + struct.pack("<I", 20)
        + b"WEBP"
        + b"VP8X"
        + struct.pack("<I", 10)
        + b"\x00" * 4
        + _24bit(width - 1)
        + _24bit(height - 1)
        + b"\x00" * 32
    )


def _webp_vp8_lossy(width: int, height: int) -> bytes:
    bits = (width & 0x3FFF) | ((height & 0x3FFF) << 14)
    dims = bytes([bits & 0xFF, (bits >> 8) & 0xFF, (bits >> 16) & 0xFF])
    return (
        b"RIFF"
        + struct.pack("<I", 20)
        + b"WEBP"
        + b"VP8 "
        + struct.pack("<I", 10)
        + b"\x9d\x01\x2a"
        + dims
        + b"\x00" * 32
    )


def _webp_vp8l(width: int, height: int) -> bytes:
    bits = ((width - 1) & 0x3FFF) | (((height - 1) & 0x3FFF) << 14)
    payload = bytes([bits & 0xFF, (bits >> 8) & 0xFF, (bits >> 16) & 0xFF, (bits >> 24) & 0xFF])
    return (
        b"RIFF"
        + struct.pack("<I", 20)
        + b"WEBP"
        + b"VP8L"
        + struct.pack("<I", 5)
        + b"\x2f"
        + payload
        + b"\x00" * 32
    )


def _jpeg(width: int, height: int) -> bytes:
    # SOF0 payload: 精度(1) 高(2) 宽(2) 分量数(1) 分量(3) = 9 字节, 段长 9+2=11
    payload = b"\x08" + struct.pack(">HH", height, width) + b"\x01\x01\x11\x00"
    return b"\xff\xd8\xff\xc0" + struct.pack(">H", len(payload) + 2) + payload + b"\xff\xd9"


@pytest.fixture
def image_dir(tmp_path: Path) -> Path:
    """写入手工构造的各格式图片, 返回目录路径。"""
    files = {
        "a.png": _png(7, 9),
        "a.gif": _gif(12, 34),
        "a.bmp": _bmp(56, -78),  # 高度为负, 应取绝对值
        "a_vp8x.webp": _webp_vp8x(100, 60),
        "a_vp8_lossy.webp": _webp_vp8_lossy(300, 150),
        "a_vp8l.webp": _webp_vp8l(200, 100),
        "a.jpg": _jpeg(20, 30),
        "a.jpeg": _jpeg(64, 64),
    }
    for name, content in files.items():
        (tmp_path / name).write_bytes(content)
    return tmp_path


# --------------------------------------------------------------------------- #
# 各格式解析
# --------------------------------------------------------------------------- #
def test_png_size(image_dir: Path):
    assert get_image_size(image_dir / "a.png") == (7, 9)


def test_gif_size(image_dir: Path):
    assert get_image_size(image_dir / "a.gif") == (12, 34)


def test_bmp_size_with_negative_height_abs(image_dir: Path):
    assert get_image_size(image_dir / "a.bmp") == (56, 78)


def test_webp_vp8x_size(image_dir: Path):
    assert get_image_size(image_dir / "a_vp8x.webp") == (100, 60)


def test_webp_vp8_lossy_size(image_dir: Path):
    assert get_image_size(image_dir / "a_vp8_lossy.webp") == (300, 150)


def test_webp_vp8l_size(image_dir: Path):
    assert get_image_size(image_dir / "a_vp8l.webp") == (200, 100)


def test_jpeg_size_both_suffixes(image_dir: Path):
    assert get_image_size(image_dir / "a.jpg") == (20, 30)
    assert get_image_size(image_dir / "a.jpeg") == (64, 64)


# --------------------------------------------------------------------------- #
# 异常输入兜底
# --------------------------------------------------------------------------- #
def test_non_image_file_returns_none(tmp_path: Path):
    text_file = tmp_path / "note.txt"
    text_file.write_text("hello world")

    assert get_image_size(text_file) is None


def test_empty_file_returns_none(tmp_path: Path):
    empty = tmp_path / "empty.png"
    empty.write_bytes(b"")

    assert get_image_size(empty) is None


def test_missing_file_returns_none(tmp_path: Path):
    assert get_image_size(tmp_path / "not_exist.png") is None


def test_truncated_png_returns_none(tmp_path: Path):
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00")

    assert get_image_size(broken) is None


# --------------------------------------------------------------------------- #
# 真实样例 (仓库自带 asset/RAG.png)
# --------------------------------------------------------------------------- #
def test_real_png_sample(project_root: Path):
    sample = project_root / "asset" / "RAG.png"
    assert sample.exists(), "asset/RAG.png 不存在"

    size = get_image_size(sample)
    assert size is not None
    assert size[0] > 0 and size[1] > 0
