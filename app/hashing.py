"""文件内容哈希：精确去重依据。"""
import hashlib
from pathlib import Path


def sha256_file(path, chunk_size: int = 1024 * 1024) -> str:
    """计算文件 SHA-256，返回十六进制字符串。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()
