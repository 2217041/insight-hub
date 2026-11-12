"""W10 冒烟：DOCX / PDF 解析 + 父子块 + 分块预览。

生成两份真实文件（python-docx / pymupdf 造），上传后检查：
1. 解析成功、状态到 ready；
2. 同时存在父块（parent_id 为空）和子块（parent_id 非空）；
3. order_index 递增；
4. 章节路径、页码、表格块都在。

用法：python scripts/w10_smoke.py
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
import uuid

import httpx

BASE = os.environ.get("BASE", "http://127.0.0.1:8000")


def make_docx() -> bytes:
    from docx import Document

    doc = Document()
    doc.add_heading("差旅报销制度", level=1)
    doc.add_paragraph("本制度适用于公司全体员工的国内差旅与因公外出。")

    doc.add_heading("住宿标准", level=2)
    doc.add_paragraph("一线城市每晚不超过 600 元；二线城市不超过 400 元。")
    doc.add_paragraph("超标部分需部门负责人书面说明。")

    doc.add_heading("审批流程", level=2)
    doc.add_paragraph("员工提交 → 直属主管审批 → 财务复核 → 打款。超过 5000 元需加签。")

    table = doc.add_table(rows=3, cols=2)
    table.cell(0, 0).text = "城市级别"
    table.cell(0, 1).text = "住宿上限"
    table.cell(1, 0).text = "一线"
    table.cell(1, 1).text = "600"
    table.cell(2, 0).text = "二线"
    table.cell(2, 1).text = "400"

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def make_pdf() -> bytes:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    y = 72
    for line in [
        "Quarterly Report",
        "Revenue in Q3 reached 12.5 million RMB, up 18% year over year.",
        "The East China region contributed the largest share.",
        "",
        "Cost control remained a priority during the quarter.",
        "Headcount grew by 12 people across three teams.",
    ]:
        page.insert_text((72, y), line, fontsize=12)
        y += 24

    page2 = doc.new_page()
    page2.insert_text((72, 72), "Appendix: detailed breakdown by region.", fontsize=12)
    page2.insert_text((72, 96), "East 5.2M, North 3.1M, South 2.8M, West 1.4M.", fontsize=12)

    data = doc.tobytes()
    doc.close()
    return data


def upload(client: httpx.Client, name: str, data: bytes, mime: str) -> dict:
    r = client.post("/api/documents", files={"file": (name, data, mime)})
    if r.status_code != 201:
        raise RuntimeError(f"上传失败 {r.status_code}: {r.text[:200]}")
    return r.json()["document"]


def wait_ready(client: httpx.Client, doc_id: str, timeout: float = 60) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        d = client.get(f"/api/documents/{doc_id}").json()
        if d["status"] in ("ready", "failed"):
            return d
        time.sleep(0.5)
    raise TimeoutError("解析超时")


def inspect(client: httpx.Client, doc: dict, label: str) -> bool:
    chunks = client.get(f"/api/documents/{doc['id']}/chunks").json()["items"]
    parents = [c for c in chunks if c["parent_id"] is None]
    children = [c for c in chunks if c["parent_id"]]
    tables = [c for c in chunks if c["content_type"] == "table"]
    sections = {c["section_path"] for c in chunks if c["section_path"]}
    orders = [c["order_index"] for c in chunks]

    print(f"\n=== {label} ===")
    print(f"  状态={doc['status']} 子块数={doc['chunk_count']}")
    print(f"  父块 {len(parents)} / 子块 {len(children)} / 表格块 {len(tables)}")
    print(f"  章节路径: {sorted(sections)[:4]}")
    print(f"  order_index 递增: {orders == sorted(orders)}")

    for c in parents[:2]:
        print(f"  [父 p{c['page']} {c['section_path'][:12]!r}] {c['content'][:50]!r}")
    for c in children[:2]:
        print(f"  [子 p{c['page']} {c['token_count']}tok] {c['content'][:50]!r}")
    if tables:
        print(f"  [表格] {tables[0]['content'][:60]!r}")

    return bool(parents) and bool(children) and orders == sorted(orders)


def main() -> int:
    c = httpx.Client(base_url=BASE, timeout=120)
    email = f"w10-{uuid.uuid4().hex[:8]}@example.com"
    c.post("/api/auth/register", json={"email": email, "password": "Passw0rd!23"})
    token = c.post("/api/auth/login", json={"email": email, "password": "Passw0rd!23"}).json()[
        "access_token"
    ]
    c.headers["Authorization"] = f"Bearer {token}"
    print(f"用户 {email}")

    ok = True

    docx_doc = upload(c, "差旅报销制度.docx", make_docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    docx_doc = wait_ready(c, docx_doc["id"])
    ok &= inspect(c, docx_doc, "DOCX（含标题层级与表格）")

    pdf_doc = upload(c, "quarterly.pdf", make_pdf(), "application/pdf")
    pdf_doc = wait_ready(c, pdf_doc["id"])
    ok &= inspect(c, pdf_doc, "PDF（两页）")

    print("\n✅ W10 冒烟通过" if ok else "\n❌ 有问题")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())