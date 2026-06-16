"""
LaTeX .tex 生成模块
读取结构化校对 JSON + 原始 .md → 生成 paracol 双栏 .tex 文件。
"""
import json
import os
import re

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
TEMPLATE_FILE = os.path.join(TEMPLATE_DIR, "proofread_template.tex")

# LaTeX 特殊字符（按转义顺序：\ 必须最先处理）
_LATEX_SPECIAL = [
    ("\\", r"\textbackslash "),
    ("&", r"\&"),
    ("%", r"\%"),
    ("$", r"\$"),
    ("#", r"\#"),
    ("_", r"\_"),
    ("{", r"\{"),
    ("}", r"\}"),
    ("~", r"\textasciitilde "),
    ("^", r"\textasciicircum "),
]


def _escape_text(text: str) -> str:
    """转义 LaTeX 特殊字符（\ 映射为 \textbackslash 避免转义歧义）"""
    for char, replacement in _LATEX_SPECIAL:
        text = text.replace(char, replacement)
    return text


def _unescape_math(text: str) -> str:
    """反向转义：将公式内的转义字符恢复（仅处理 \textbackslash 等长命令回退）"""
    # 在 $ 内的 \textbackslash 恢复为反斜杠
    reverse_map = [
        (r"\textbackslash ", "\\"),
        (r"\&", "&"),
        (r"\%", "%"),
        (r"\$", "$"),
        (r"\#", "#"),
        (r"\_", "_"),
        (r"\{", "{"),
        (r"\}", "}"),
        (r"\textasciitilde ", "~"),
        (r"\textasciicircum ", "^"),
    ]
    for escaped, original in reverse_map:
        text = text.replace(escaped, original)
    return text


def _split_math(text: str) -> list[tuple[str, bool]]:
    """将文本分割为 (片段, 是否数学模式) 列表"""
    parts = re.split(r"(\$\$[\s\S]*?\$\$|\$[^$]*?\$)", text)
    result = []
    for part in parts:
        if not part:
            continue
        in_math = part.startswith("$")
        result.append((part, in_math))
    return result


def _apply_to_paragraph(paragraph: str, corrections: list[dict]) -> list[dict]:
    """在单个段落内按数学边界切分后查找并应用修改项"""
    # 先按数学边界切分
    segments = _split_math(paragraph)

    # 对每个 segment 找 hits（跳过数学模式内的搜索）
    all_segs = []
    for seg_text, in_math in segments:
        hits = []
        if not in_math:
            for corr in corrections:
                search_key = corr.get("original") or corr.get("location", "")
                if not search_key:
                    continue
                idx = seg_text.find(search_key)
                if idx >= 0:
                    hits.append((idx, len(search_key), corr))

        if not hits:
            all_segs.append({"text": seg_text, "in_math": in_math, "correction": None})
            continue

        hits.sort(key=lambda x: x[0])
        pos = 0
        for start, length, corr in hits:
            if start > pos:
                all_segs.append({"text": seg_text[pos:start], "in_math": in_math, "correction": None})
            all_segs.append({"text": seg_text[start:start + length], "in_math": in_math, "correction": corr})
            pos = start + length
        if pos < len(seg_text):
            all_segs.append({"text": seg_text[pos:], "in_math": in_math, "correction": None})

    return all_segs


def _escape_md(text: str) -> str:
    """转义 Markdown 文本：保护数学公式，转义其余内容"""
    parts = _split_math(text)
    result = []
    for seg_text, in_math in parts:
        if in_math:
            result.append(seg_text)
        else:
            result.append(_escape_text(seg_text))
    return "".join(result)


def _convert_images(text: str) -> str:
    """将 Markdown 图片语法转换为 LaTeX includegraphics"""
    return re.sub(
        r"!\[.*?\]\((.*?)\)",
        r"\\includegraphics[width=\\linewidth]{\1}",
        text,
    )


def _escape_segment(seg: dict) -> str:
    """对 segment 的 text 做 LaTeX 转义（非数学模式）"""
    if seg.get("in_math"):
        return seg["text"]
    return _escape_text(seg["text"])


def _render_segment_text(seg: dict) -> str:
    """渲染一个 segment 的文本（应用修改标记）。correction 文本不转义（LaTeX 原生）。"""
    text = _escape_segment(seg)
    corr = seg["correction"]
    if corr is None:
        return text

    ctype = corr["type"]
    if ctype == "text":
        correction_text = corr.get("correction", "")
        return r"\corrtext{" + text + "}{" + correction_text + "}"
    elif ctype == "rewrite":
        return r"\corrrewrite{" + text + "}"
    elif ctype == "region":
        return r"\corrregion{" + text + "}"
    return text


def build_paracol_content(md_content: str, corrections: list[dict]) -> str:
    """从 Markdown 内容和修改列表构建 paracol 双栏 LaTeX 内容。"""

    corrections = corrections or []

    # 2. 逐段落处理
    paragraphs = [p for p in md_content.strip().split("\n\n") if p.strip()]

    result_parts = [r"\begin{paracol}{2}", ""]

    for para in paragraphs:
        segments = _apply_to_paragraph(para, corrections)
        has_correction = any(s.get("correction") is not None for s in segments)

        if not has_correction:
            # 全段无修改：左栏原文（先转义，再转换图片）
            result_parts.append(_convert_images(_escape_md(para)))
            result_parts.append("")
        else:
            # 渲染左栏：逐 segment，有修改的加标记
            left_parts = []
            for seg in segments:
                if seg["correction"] is None:
                    if seg.get("in_math"):
                        left_parts.append(seg["text"])
                    else:
                        left_parts.append(_escape_text(seg["text"]))
                else:
                    left_parts.append(_render_segment_text(seg))

            result_parts.append(_convert_images("".join(left_parts)))

            # 切换到右栏
            result_parts.append(r"\switchcolumn")
            result_parts.append("")

            # 收集该段落中所有修改项
            para_corrections = []
            for seg in segments:
                corr = seg.get("correction")
                if corr and corr not in para_corrections:
                    para_corrections.append(corr)

            for corr in para_corrections:
                reason = _escape_text(corr.get("reason", ""))
                ctype = corr["type"]

                if ctype == "text":
                    correction_text = _escape_text(corr.get("correction", ""))
                    right_text = f"修改为：{correction_text}"
                else:
                    correction_text = _escape_text(corr.get("correction", ""))
                    right_text = correction_text

                result_parts.append(
                    r"\correctionbox{\textbf{" + reason + r"}：" + right_text + "}"
                )
                result_parts.append(r"\bigskip")
                result_parts.append("")

            result_parts.append(r"\switchcolumn*")
            result_parts.append("")

    result_parts.append(r"\end{paracol}")
    return "\n".join(result_parts)


def generate_tex(json_path: str, md_path: str, output_path: str) -> str:
    """读取校对 JSON 和原始 .md，生成 .tex 文件。

    Args:
        json_path: _校对数据.json 文件路径
        md_path: 原始题目 .md 文件路径
        output_path: 输出 .tex 文件路径

    Returns:
        生成的 .tex 文件路径
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    with open(md_path, "r", encoding="utf-8") as f:
        md_content = f.read()

    corrections = data.get("corrections", [])

    # 构建 paracol 内容
    paracol_content = build_paracol_content(md_content, corrections)

    # 获取标题
    title = os.path.splitext(os.path.basename(md_path))[0]

    # 读取模板
    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        template = f.read()

    # 填充模板
    full_tex = template.replace("{{CONTENT}}", paracol_content)
    full_tex = full_tex.replace(r"\title{校对报告}", r"\title{" + title + "}")

    # 写入输出文件
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_tex)

    return output_path
