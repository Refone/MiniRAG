"""本地 Token 计算工具 (Qwen tokenizer, 离线)。

加载固定项目资源 ``src/common/model/qwen.tiktoken`` 词表, 用 tiktoken 离线计算
token, 与阿里云 AI 搜索开放平台 Token 计算 API 的结果一致:
    - "苹果"           -> 1 token
    - "测试用例"       -> 3 tokens
    - "OpenSearch"     -> 2 tokens
    - "测试token计算接口" -> 4 tokens

计算过程完全离线, 不发起任何网络请求。

参考: https://www.alibabacloud.com/help/zh/open-search/search-platform/developer-reference/token-calculation
"""

from __future__ import annotations

import base64
import unicodedata
from functools import lru_cache
from pathlib import Path

import tiktoken

# 固定项目资源: 词表文件在 src/common/model/ 下（数据文件依赖, 不是模块依赖）
_VOCAB_PATH = Path(__file__).parents[1] / "model" / "qwen.tiktoken"

# --------------------------------------------------------------------------- #
# Qwen tokenizer 的 tiktoken 配置 (与 dashscope 内置 QwenTokenizer 一致)
# --------------------------------------------------------------------------- #
_PAT_STR = (
    r"""(?i:'s|'t|'re|'ve|'m|'ll|'d)|[^\r\n\p{L}\p{N}]?\p{L}+|\p{N}|"""
    r""" ?[^\s\p{L}\p{N}]+[\r\n]*|\s*[\r\n]+|\s+(?!\S)|\s+"""
)
_ENDOFTEXT = "<|endoftext|>"
_IMSTART = "<|im_start|>"
_IMEND = "<|im_end|>"
_EXTRAS = tuple(f"<|extra_{i}|>" for i in range(205))
_SPECIAL_START_ID = 151643
_SPECIAL_TOKENS = tuple(
    enumerate((_ENDOFTEXT, _IMSTART, _IMEND) + _EXTRAS, start=_SPECIAL_START_ID)
)


@lru_cache(maxsize=1)
def _load_encoding() -> tiktoken.Encoding:
    """加载词表并构建 tiktoken 编码器 (进程内只加载一次)。"""
    with open(_VOCAB_PATH, "rb") as f:
        contents = f.read()

    mergeable_ranks = {
        base64.b64decode(token): int(rank)
        for token, rank in (line.split() for line in contents.splitlines() if line)
    }
    return tiktoken.Encoding(
        name="qwen",
        pat_str=_PAT_STR,
        mergeable_ranks=mergeable_ranks,
        special_tokens={tok: idx for idx, tok in _SPECIAL_TOKENS},
    )


def compute_token(text: str) -> int:
    """计算文本的 token 数 (本地离线计算)。

    参数:
        text: 待计数的文本。

    返回:
        文本对应的 token 数。
    """
    text = unicodedata.normalize("NFC", text)
    return len(_load_encoding().encode(text, allowed_special="all"))


__all__ = ["compute_token"]


if __name__ == "__main__":
    texts = [
        "测试token计算接口",
        "IPhone",
        "250",
        "HAK 180 烫金机",
        "IPhone 17 Pro Max",
    ]
    for text in texts:
        print(text, compute_token(text))
