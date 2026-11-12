"""生成测试用知识库文档：DOCX + PDF + 测试问题清单。

设计目标——让每一步都能被验证：
1. 多级标题 → 验证 section_path 是否保留；
2. 表格 → 验证表格是否被整体抽成块（而不是按行切碎）；
3. 大量具体数字/编号（政策号、税号、金额、天数）→ 验证检索能否命中"专有名词/数字"；
4. 篇幅足够 → 验证父子块切分（预计 8–15 个父块、20+ 子块）；
5. 附"测试问题清单"，含 3 个文档里**没有**的问题 → 验证拒答。

用法：
    cd apps/api
    .\\.venv\\Scripts\\python.exe ..\\..\\examples\\knowledge-base\\generate.py
"""

from __future__ import annotations

import io
from pathlib import Path

OUT = Path(__file__).parent

# --------------------------------------------------------------------------- #
# 文档内容（结构化定义，DOCX / PDF / Markdown 三份产物同源）
# --------------------------------------------------------------------------- #
TITLE = "云雀科技 · 差旅与费用报销手册"
META = "政策编号：LX-HR-2026-03　｜　版本：v3.2　｜　生效日期：2026-03-01　｜　解释部门：人力资源部 / 财务部"

SECTIONS: list[dict] = [
    {
        "heading": "一、适用范围",
        "paras": [
            "本手册适用于云雀科技有限公司（以下简称“公司”）全体正式员工、实习生，"
            "以及经批准的外包驻场人员。外包人员的差旅标准以合同约定为准，合同未约定的参照本手册执行。",
            "本手册不适用于董事会成员、外部顾问与来访客户。",
            "自本手册生效之日起，此前发布的差旅与报销相关规定同时废止；如有冲突，以本手册为准。",
        ],
    },
    {
        "heading": "二、出差审批流程",
        "paras": [
            "除紧急情况外，所有出差须在出发前 3 个工作日内通过 OA 系统提交《出差申请单》，"
            "写明出差事由、目的地、起止日期与预算金额。",
            "审批链路为：直属主管 → 部门负责人（单次预算超过 8000 元时）→ 财务备案。"
            "预算未超过 8000 元的，仅需直属主管审批。",
            "紧急出差可先出发后补单，但必须在返回后 2 个工作日内补齐审批，"
            "逾期未补单的行程不予报销。",
            "境外差旅须提前 10 个工作日提交申请，并附邀请函或会议通知。",
        ],
    },
    {
        "heading": "三、交通标准",
        "paras": [
            "火车：单程行驶时间在 3 小时以内的，原则上乘坐二等座；总监及以上职级可乘坐一等座。",
            "飞机：原则上乘坐经济舱；单程飞行时间超过 5 小时且职级为 P8 及以上的，可乘坐公务舱。",
            "市内交通：打车须在报销单中注明事由与起终点；单次金额超过 150 元的，需直属主管书面确认。",
            "自驾：按 0.8 元/公里给予补贴，需提供导航行程单或过路费凭证，不再另行报销油费。",
        ],
    },
    {
        "heading": "四、住宿标准",
        "paras": [
            "住宿费按目的地城市级别执行上限标准，以实际入住晚数结算，见下表。",
        ],
        "table": [
            ["城市级别", "代表城市", "住宿上限（元/晚）", "备注"],
            ["一线", "北京、上海、深圳、广州", "650", "广交会等特殊时期可上浮 30%"],
            ["新一线", "杭州、成都、武汉、西安、南京", "480", "需提前报备"],
            ["二线", "其他省会城市", "380", "—"],
            ["三线及以下", "地级市及以下", "300", "—"],
        ],
        "paras_after": [
            "超标处理：住宿费超标在 20% 以内的，由部门负责人书面同意后可全额报销；"
            "超过 20% 的部分由个人自理。",
            "同性别同事同行时原则上合住，合住节省的费用不额外返还。",
        ],
    },
    {
        "heading": "五、餐饮与出差补贴",
        "paras": [
            "出差期间按自然日发放补贴：一线城市 120 元/天，新一线 100 元/天，二线 80 元/天，"
            "三线及以下 60 元/天。",
            "补贴按自然日计算，出发当日与返回当日各按半天计。",
            "已由公司统一安排用餐的，当日补贴减半；全天由主办方提供餐食的，当日不发补贴。",
            "实习生按上述标准的 80% 执行。",
        ],
    },
    {
        "heading": "六、报销时限与凭证要求",
        "paras": [
            "报销单须在行程结束后 15 个自然日内提交。逾期提交需部门负责人特批；"
            "超过 60 天的不予受理。",
            "发票抬头必须为“云雀科技有限公司”，纳税人识别号 91110108MA01XXXXXX。"
            "抬头错误的发票一律退回。",
            "电子发票须提交 PDF 原件，系统会自动查重，重复报销将被驳回并记录在案。",
            "发票丢失的，可提供发票复印件、情况说明与主管签字，经财务审核后按 80% 报销。",
        ],
    },
    {
        "heading": "七、特殊场景",
        "paras": [
            "会议与培训：主办方已统一安排食宿的，不再发放住宿费与餐饮补贴。",
            "加班打车：22:00 之后因加班产生的打车费可报销，须附加班审批记录。",
            "国际差旅：按目的地城市分级执行，汇率按报销当日的中间价折算。",
            "因公产生的签证费、保险费、疫苗费用可全额报销。",
        ],
    },
    {
        "heading": "八、常见问题",
        "paras": [
            "问：出差期间的周末是否计算补贴？答：计算，按自然日发放。",
            "问：可以住民宿吗？答：可以，但须提供正规发票，且金额不超过对应城市级别上限。",
            "问：同事代付的费用如何报销？答：由实际支付人提交报销，并附代付说明。",
            "问：机票改签费能报销吗？答：因公改签可报销，因私改期由个人承担。",
            "问：报销多久到账？答：审批流程完成后 5 个工作日内打款。",
            "问：实习生有出差补贴吗？答：有，按标准的 80% 执行。",
            "问：出差期间可以延长停留吗？答：因私延长期间的住宿与补贴由个人承担。",
        ],
    },
    {
        "heading": "九、附则",
        "paras": [
            "本手册由人力资源部与财务部共同解释，自 2026 年 3 月 1 日起施行。",
            "版本记录：v1.0（2023-05）、v2.0（2024-09）、v3.0（2025-06）、v3.2（2026-03）。",
            "本手册每两年复审一次；如遇重大政策调整，可提前修订并另行通知。",
        ],
    },
]


def all_paragraphs() -> list[tuple[str, list[str]]]:
    """展平成 (段落文本, 所属章节) 便于生成 PDF/Markdown。"""
    out: list[tuple[str, list[str]]] = []
    for sec in SECTIONS:
        out.append((sec["heading"], []))
        for p in sec.get("paras", []):
            out.append((p, []))
        if sec.get("table"):
            rows = sec["table"]
            out.append(("TABLE:" + " | ".join(rows[0]), []))
            for row in rows[1:]:
                out.append(("TABLEROW:" + " | ".join(row), []))
        for p in sec.get("paras_after", []):
            out.append((p, []))
    return out


# --------------------------------------------------------------------------- #
# DOCX
# --------------------------------------------------------------------------- #
def gen_docx(path: Path) -> None:
    from docx import Document
    from docx.shared import Pt

    doc = Document()
    doc.add_heading(TITLE, level=0)
    meta = doc.add_paragraph(META)
    meta.runs[0].font.size = Pt(9)

    for sec in SECTIONS:
        doc.add_heading(sec["heading"], level=1)
        for p in sec.get("paras", []):
            doc.add_paragraph(p)

        if sec.get("table"):
            rows = sec["table"]
            table = doc.add_table(rows=len(rows), cols=len(rows[0]))
            table.style = "Table Grid"
            for r, row in enumerate(rows):
                for c, cell in enumerate(row):
                    table.cell(r, c).text = cell

        for p in sec.get("paras_after", []):
            doc.add_paragraph(p)

    doc.save(path)


# --------------------------------------------------------------------------- #
# PDF（用中文字体，避免方块）
# --------------------------------------------------------------------------- #
def gen_pdf(path: Path) -> None:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    y = 60
    margin = 60
    line_height = 18
    max_y = 780

    def new_page() -> tuple:
        nonlocal page, y
        page = doc.new_page()
        y = 60
        return page, y

    def write(text: str, size: int = 10, bold: bool = False) -> None:
        nonlocal y
        # 简单折行：按字数估算，中文 1 字 ≈ size 宽
        per_line = int((page.rect.width - margin * 2) / size)
        chunks = [text[i : i + per_line] for i in range(0, len(text), per_line)] or [""]
        for line in chunks:
            if y > max_y:
                new_page()
            page.insert_text(
                (margin, y), line, fontsize=size,
                fontname="china-s",  # pymupdf 内置中文字体
            )
            y += line_height if size >= 10 else line_height - 4
        y += 4

    write(TITLE, 18)
    write(META, 8)
    y += 6

    for sec in SECTIONS:
        write(sec["heading"], 13)
        for p in sec.get("paras", []):
            write(p)
        if sec.get("table"):
            for row in sec["table"]:
                write(" | ".join(row), 9)
            y += 4
        for p in sec.get("paras_after", []):
            write(p)

    doc.save(path)


# --------------------------------------------------------------------------- #
# Markdown（方便直接在网页里对照）
# --------------------------------------------------------------------------- #
def gen_markdown(path: Path) -> None:
    lines = [f"# {TITLE}", "", f"> {META}", ""]
    for sec in SECTIONS:
        lines.append(f"## {sec['heading']}")
        lines.append("")
        for p in sec.get("paras", []):
            lines.append(p)
            lines.append("")
        if sec.get("table"):
            rows = sec["table"]
            lines.append("| " + " | ".join(rows[0]) + " |")
            lines.append("|" + "---|" * len(rows[0]))
            for row in rows[1:]:
                lines.append("| " + " | ".join(row) + " |")
            lines.append("")
        for p in sec.get("paras_after", []):
            lines.append(p)
            lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------- #
# 测试问题清单
# --------------------------------------------------------------------------- #
QUESTIONS = """# 知识库测试问题清单

> 先把 `云雀科技-差旅费用报销手册.docx`（或 .pdf）传到「文档」页，等状态变成「已完成」，再回对话页提问。
> 每题的**期望答案**都能在文档里找到；最后 3 题文档里**没有答案**，用来验证拒答。

## 一、简单事实（验证基础检索）

| # | 问题 | 期望答案要点 |
|---|---|---|
| 1 | 这份手册的政策编号是多少？ | LX-HR-2026-03 |
| 2 | 住宿费超标多少以内可以全报？ | 20% 以内，需部门负责人书面同意 |
| 3 | 报销单要在行程结束后几天内提交？ | 15 个自然日内 |
| 4 | 逾期多久就不予受理了？ | 超过 60 天 |
| 5 | 自驾的补贴标准是多少？ | 0.8 元/公里 |
| 6 | 发票抬头和税号是什么？ | 云雀科技有限公司 / 91110108MA01XXXXXX |
| 7 | 实习生出差补贴按什么标准？ | 标准的 80% |

## 二、表格类（验证表格是否被整体抽取）

| # | 问题 | 期望答案要点 |
|---|---|---|
| 8 | 杭州的住宿上限是多少？ | 480 元/晚（新一线） |
| 9 | 一线城市包括哪些？ | 北京、上海、深圳、广州 |
| 10 | 三线及以下的住宿上限？ | 300 元/晚 |

## 三、多条件 / 推理（验证是否能组合多个段落）

| # | 问题 | 期望答案要点 |
|---|---|---|
| 11 | 一次预算 10000 元的出差，需要谁审批？ | 直属主管 + 部门负责人（超 8000 元） |
| 12 | 单程飞行 6 小时，P7 员工能坐公务舱吗？ | 不能，需 P8 及以上 |
| 13 | 出差 3 天（一线城市），补贴一共多少？ | 出发/返回各半天 + 中间 2 天 = 2 天 × 120 = 240 元 |
| 14 | 发票丢了还能报销吗？能报多少？ | 可以，复印件 + 情况说明 + 主管签字，按 80% 报销 |

## 四、应拒答（文档里没有的内容）

| # | 问题 | 期望行为 |
|---|---|---|
| 15 | 公司的年假有几天？ | 明确说明手册未涉及（这是差旅报销手册，不含年假） |
| 16 | 股票期权的行权价格是多少？ | 明确说明未找到 |
| 17 | 产假可以休多久？ | 明确说明未找到 |

> ⚠️ 注意：**当前阶段（W10）还没有接入检索**，模型只看得到对话历史，
> 回答不了上述任何问题。真正的"基于文档回答"要等 W11（向量化 + 混合检索）。
> 这份清单是给 W11 之后验证用的。

## 五、怎么判断检索质量（W11 之后）

1. 回答里是否给出**页码/章节**（引用溯源）；
2. 第 15–17 题是否**明确拒答**而不是编造；
3. 第 8–10 题（表格类）能否答对——这是检验表格抽取是否有效的关键；
4. 第 11–14 题（多条件）能否组合多个段落作答。
"""


def main() -> None:
    docx_path = OUT / "云雀科技-差旅费用报销手册.docx"
    pdf_path = OUT / "云雀科技-差旅费用报销手册.pdf"
    md_path = OUT / "云雀科技-差旅费用报销手册.md"
    q_path = OUT / "测试问题清单.md"

    gen_docx(docx_path)
    gen_pdf(pdf_path)
    gen_markdown(md_path)
    q_path.write_text(QUESTIONS, encoding="utf-8")

    for p in (docx_path, pdf_path, md_path, q_path):
        print(f"  {p.name:45s} {p.stat().st_size / 1024:7.1f} KB")

    # 粗估块数，便于对照
    total_chars = sum(len(p) for p, _ in all_paragraphs())
    print(f"\n正文字数约 {total_chars}，预计父块 {total_chars // 900 + 1} 个、子块 {total_chars // 260 + 1} 个")


if __name__ == "__main__":
    main()