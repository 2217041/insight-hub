"""文档解析与分块（W10）。

W5 的版本只会按空行切段落，这周升级成三件事：

1. **多格式解析**：PDF（含双栏、表格）、DOCX、Markdown、TXT；
2. **结构化**：每个块带页码与章节路径（`section_path`）——这是 W12 引用溯源的命根子；
3. **父子块**：父块 ~1000 字用于生成上下文，子块 ~260 字用于检索。

关于"为什么父子块"：
- 只切小块：检索准，但喂给模型的上下文残缺；
- 只切大块：上下文全，但检索噪声大；
- 父子块：**子块负责"被找到"，父块负责"被理解"**，两边都要。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# 分块参数（W10 先定常量，W11 会做实验对比不同取值）
PARENT_SIZE = 1000
CHILD_SIZE = 260
MIN_BLOCK_CHARS = 12


class UnsupportedFormat(Exception):
    pass


@dataclass
class Block:
    """解析出来的最小单元：一个段落 / 一个表格 / 一行标题。"""

    text: str
    page: int = 1
    section: str = ""
    kind: str = "text"  # text | table | heading


@dataclass
class ChunkGroup:
    """一个父块 + 它的子块。"""

    parent: str
    children: list[str] = field(default_factory=list)
    page: int = 1
    section: str = ""
    kind: str = "text"


# --------------------------------------------------------------------------- #
# 清洗
# --------------------------------------------------------------------------- #
def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\u3000]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _strip_repeated_lines(pages: list[str]) -> list[str]:
    """去掉页眉页脚：在多页中重复出现的短行。

    做法朴素但有效：统计出现次数，超过页数一半且长度 < 60 的行删掉。
    """
    if len(pages) < 3:
        return pages
    counter: dict[str, int] = {}
    for page in pages:
        for line in {ln.strip() for ln in page.splitlines() if ln.strip()}:
            if len(line) < 60:
                counter[line] = counter.get(line, 0) + 1
    threshold = max(2, len(pages) // 2)
    repeated = {line for line, n in counter.items() if n >= threshold}
    cleaned = []
    for page in pages:
        kept = [ln for ln in page.splitlines() if ln.strip() not in repeated]
        cleaned.append("\n".join(kept))
    return cleaned


# --------------------------------------------------------------------------- #
# 各格式解析
# --------------------------------------------------------------------------- #
def _blocks_from_markdown(text: str) -> list[Block]:
    blocks: list[Block] = []
    section = ""
    for para in re.split(r"\n\s*\n", _normalize(text)):
        para = para.strip()
        if not para:
            continue
        if para.startswith("#"):
            section = para.lstrip("#").strip()[:200]
            blocks.append(Block(para, 1, section, "heading"))
            continue
        blocks.append(Block(para, 1, section, "text"))
    return blocks


def _blocks_from_pdf(data: bytes) -> list[Block]:
    """PDF：按栏 + 纵向顺序还原阅读顺序。

    双栏 PDF 直接按 y 排序会串行，所以先按 x 判断左/右栏，再按 y 排序。
    """
    import pymupdf  # 延迟导入：没装 pymupdf 也不影响其他格式

    blocks: list[Block] = []
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        for page_no, page in enumerate(doc, start=1):
            width = page.rect.width
            raw = page.get_text("blocks")  # (x0, y0, x1, y1, text, block_no, type)
            # 按"先栏、后行"排序
            raw.sort(key=lambda b: (0 if (b[0] + b[2]) / 2 < width / 2 else 1, b[1]))
            for item in raw:
                text = _normalize(item[4])
                if len(text) < 1:
                    continue
                blocks.append(Block(text, page_no, "", "text"))

            # 表格：单独抽出来，转成 Markdown 表格整体成块，避免按行切碎
            try:
                for table in page.find_tables():
                    rows = table.extract()
                    if not rows or len(rows) < 2:
                        continue
                    md = "\n".join(
                        "| " + " | ".join((c or "").strip() for c in row) + " |"
                        for row in rows
                    )
                    blocks.append(Block(md, page_no, "", "table"))
            except Exception:  # noqa: BLE001 - 老版本/复杂版面可能不支持
                pass
    return blocks


def _blocks_from_docx(data: bytes) -> list[Block]:
    import io

    from docx import Document as Docx

    blocks: list[Block] = []
    section = ""
    doc = Docx(io.BytesIO(data))
    for para in doc.paragraphs:
        text = _normalize(para.text)
        if not text:
            continue
        style = (para.style.name or "").lower()
        if style.startswith("heading"):
            section = text[:200]
            blocks.append(Block(text, 1, section, "heading"))
        else:
            blocks.append(Block(text, 1, section, "text"))

    for table in doc.tables:
        rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
        if len(rows) < 2:
            continue
        md = "\n".join("| " + " | ".join(row) + " |" for row in rows)
        blocks.append(Block(md, 1, section, "table"))
    return blocks


# --------------------------------------------------------------------------- #
# 对外的解析入口
# --------------------------------------------------------------------------- #
def extract_blocks(data: bytes, filename: str) -> tuple[list[Block], str]:
    """返回 (块列表, 提示信息)。提示用于告知调用方做了哪些降级处理。"""
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    note = ""

    if suffix in ("md", "markdown", "txt"):
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("gbk", errors="replace")
            note = "按 GBK 解码"
        blocks = _blocks_from_markdown(text)
    elif suffix == "pdf":
        blocks = _blocks_from_pdf(data)
        note = "PDF 已按栏排序并抽取表格"
    elif suffix in ("docx", "doc"):
        if suffix == "doc":
            raise UnsupportedFormat("旧版 .doc 请先另存为 .docx")
        blocks = _blocks_from_docx(data)
        note = "DOCX 已抽取段落与表格"
    else:
        raise UnsupportedFormat(f"暂不支持的文件类型：.{suffix}")

    blocks = [b for b in blocks if len(b.text) >= (1 if b.kind != "text" else MIN_BLOCK_CHARS)]
    if not blocks:
        raise UnsupportedFormat("文件里没有可提取的文本（可能是扫描件，需要 OCR）")
    return blocks, note


# --------------------------------------------------------------------------- #
# 分块：先聚父块，再切子块
# --------------------------------------------------------------------------- #
def _split_children(text: str, size: int) -> list[str]:
    """把父块切成子块，尽量在句子边界切。"""
    if len(text) <= size:
        return [text]

    sentences = re.split(r"(?<=[。！？；\n])", text)
    children: list[str] = []
    buf = ""
    for sent in sentences:
        if not sent:
            continue
        if buf and len(buf) + len(sent) > size:
            children.append(buf.strip())
            buf = sent
        else:
            buf += sent
    if buf.strip():
        children.append(buf.strip())
    return [c for c in children if c]


def build_chunks(blocks: list[Block]) -> list[ChunkGroup]:
    """把块聚成"父块 + 子块"的组。

    聚合规则：遇到标题变化、或累积长度超过 PARENT_SIZE 就断开。
    """
    groups: list[ChunkGroup] = []
    buf: list[str] = []
    buf_page = blocks[0].page if blocks else 1
    buf_section = ""
    buf_kind = "text"

    def flush() -> None:
        nonlocal buf, buf_page, buf_section, buf_kind
        text = "\n\n".join(buf).strip()
        if not text:
            buf = []
            return
        groups.append(
            ChunkGroup(
                parent=text,
                children=_split_children(text, CHILD_SIZE),
                page=buf_page,
                section=buf_section,
                kind=buf_kind,
            )
        )
        buf = []

    for block in blocks:
        # 标题变化 → 先收尾上一组
        if block.kind == "heading" and buf:
            flush()
        # 跨页 → 收尾：父块不跨页，否则子块的页码全都会算错（影响引用溯源）
        if buf and block.page != buf_page:
            flush()
        # 表格单独成组，不和正文混在一起
        if block.kind == "table":
            flush()
            groups.append(
                ChunkGroup(
                    parent=block.text,
                    children=_split_children(block.text, CHILD_SIZE * 2),
                    page=block.page,
                    section=block.section,
                    kind="table",
                )
            )
            continue

        if not buf:
            buf_page = block.page
            buf_section = block.section or buf_section
            buf_kind = block.kind

        buf.append(block.text)
        if sum(len(b) for b in buf) >= PARENT_SIZE:
            flush()

    flush()
    return groups