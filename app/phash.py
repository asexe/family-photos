"""感知哈希：找出「看起来一样」的照片（连拍、微信压缩版、二次保存）。

使用 dHash（差值哈希，64 位）：缩放到 9x8 灰度图，比较相邻像素亮度。
对缩放、重新压缩、轻微裁剪不敏感，且只需 Pillow，无额外依赖。
"""
from PIL import Image

HASH_BITS = 64
BLOCK_BITS = 8          # 分块索引：8 块 × 8 位
BLOCKS = HASH_BITS // BLOCK_BITS


def dhash(im, hash_size: int = 8) -> int:
    """计算 64 位 dHash。im 可为原图或缩略图（推荐用已生成的缩略图，快得多）。"""
    try:
        g = im.convert("L").resize((hash_size + 1, hash_size), Image.LANCZOS)
        px = list(g.getdata())
    except Exception:
        return 0
    bits = 0
    row_len = hash_size + 1
    for row in range(hash_size):
        base = row * row_len
        for col in range(hash_size):
            bits = (bits << 1) | (1 if px[base + col] > px[base + col + 1] else 0)
    return bits


def dhash_file(path) -> int:
    """直接从图片文件计算 dHash。"""
    try:
        with Image.open(path) as im:
            return dhash(im)
    except Exception:
        return 0


def to_hex(value: int) -> str:
    return f"{value:016x}"


def from_hex(text) -> int:
    try:
        return int(text, 16)
    except (TypeError, ValueError):
        return 0


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def block_keys(value: int):
    """把 64 位哈希切成 8 个 8 位块，用于快速找候选对。"""
    return [(value >> (BLOCK_BITS * i)) & 0xFF for i in range(BLOCKS)]
