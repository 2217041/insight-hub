"""本地文件存储（W5 临时方案）。

为什么不上 MinIO：多一个组件、多一份运维。
抽象成 save/delete 两个函数，W6 部署时换成对象存储只改这个文件。

目录结构：<storage_dir>/<tenant_id>/<doc_id><ext>
按租户分目录，运维时能直接看出归属，也方便按租户清理。
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from app.core.config import get_settings


def _safe_ext(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    # 只保留合法扩展名，避免 ..%2f 之类的路径穿越
    if not re.fullmatch(r"\.[a-z0-9]{1,8}", suffix):
        return ".bin"
    return suffix


def save(tenant_id: uuid.UUID, doc_id: uuid.UUID, filename: str, data: bytes) -> str:
    """保存文件，返回相对于 storage_dir 的路径（存进数据库，便于迁移）。"""
    base = Path(get_settings().storage_dir).resolve()
    tenant_dir = base / str(tenant_id)
    tenant_dir.mkdir(parents=True, exist_ok=True)

    relative = Path(str(tenant_id)) / f"{doc_id}{_safe_ext(filename)}"
    target = base / relative
    # 先写临时文件再替换，避免"写了一半"的文件被 worker 读到
    tmp = target.with_suffix(target.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(target)
    return str(relative)


def read(relative_path: str) -> bytes:
    base = Path(get_settings().storage_dir).resolve()
    target = (base / relative_path).resolve()
    # 防御路径穿越：解析后必须仍在 storage_dir 之内
    if not str(target).startswith(str(base)):
        raise ValueError("非法路径")
    return target.read_bytes()


def delete(relative_path: str) -> None:
    base = Path(get_settings().storage_dir).resolve()
    target = (base / relative_path).resolve()
    if str(target).startswith(str(base)) and target.exists():
        target.unlink(missing_ok=True)