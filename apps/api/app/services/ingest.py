"""文档解析与分块（W5 最小版）。

**这一步是 W10 的地盘**：真正的解析要处理双栏 PDF、表格、页眉页脚、扫描件 OCR。
这里只做三件事：
1. txt/md 按 UTF-8 读文本；
2. 按空行分段，再按目标长度聚合成块；
3. 返回 (块列表, 提示信息)。

W10 会替换 `extract_text` 与 `split_chunks`，接口保持不变。
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class RawChunk:
    content: str
    section_path: str
    page: int


class UnsupportedFormat(Exception):
    pass


def extract_text(data: bytes, filename: str) -> tuple[str, str]:
    """返回 (正文, 提示)。PDF 暂不支持，交给 W10。"""
    suffix = filename.lower().rsplit(".", 1)[-1]
    if suffix in ("txt", "md", "markdown"):
        try:
            return data.decode("utf-8"), ""
        except UnicodeDecodeError:
            # 中文文档常见 GBK，先兜一下
            return data.decode("gbk", errors="replace"), "按 GBK 解码（非 UTF-8）"
    if suffix == "pdf":
        raise UnsupportedFormat("PDF 解析在 W10 实现，当前请上传 .md 或 .txt")
    raise UnsupportedFormat(f"暂不支持的文件类型：.{suffix}")


def split_chunks(text: str, target_size: int = 800) -> list[RawChunk]:
    """按段落聚合到目标长度，尽量不切断段落。"""
    text = re.sub(r"\r\n?", "\n", text).strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[RawChunk] = []
    buffer: list[str] = []
    size = 0
    section = ""

    for para in paragraphs:
        # markdown 标题当作 section_path，供 W12 做引用展示
        if para.startswith("#"):
            section = para.lstrip("#").strip()[:200]

        if size + len(para) > target_size and buffer:
            chunks.append(RawChunk("\n\n".join(buffer), section, len(chunks) // 5 + 1))
            buffer, size = [], 0

        buffer.append(para)
        size += len(para) + 2

    if buffer:
        chunks.append(RawChunk("\n\n".join(buffer), section, len(chunks) // 5 + 1))

    return chunks