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
    """转义 LaTeX 特殊字符"""
    for char, replacement in _LATEX_SPECIAL:
        text = text.replace(char, replacement)
    return text


def _escape_preserve_math(text: str) -> str:
    """转义文本但保护 $...$ 和 $$...$$ 数学区域"""
    parts = re.split(r"(\$\$[\s\S]*?\$\$|\$[^$]*?\$)", text)
    result = []
    for part in parts:
        if not part:
            continue
        if part.startswith("$"):
            result.append(part)
        else:
            result.append(_escape_text(part))
    return "".join(result)


def _convert_images(text: str) -> str:
    """将 Markdown 图片语法转换为 LaTeX includegraphics"""
    return re.sub(
        r"!\[.*?\]\((.*?)\)",
        r"\\includegraphics[width=\\linewidth]{\1}",
        text,
    )


def _in_math(text: str, pos: int) -> bool:
    """判断 pos 位置是否在 $...$ 或 $$...$$ 数学模式内"""
    # 简单策略：计算 pos 之前的 $ 个数，奇数次则在数学模式内
    dollar_count = 0
    i = 0
    while i < pos:
        if text[i:i+2] == "$$":
            dollar_count += 1
            i += 2
            continue
        if text[i] == "$":
            dollar_count += 1
        i += 1
    return dollar_count % 2 == 1


def _find_corrections_in_paragraph(paragraph: str, corrections: list[dict]) -> list[dict]:
    """在段落中查找修改项并切分原文。

    优先精确匹配，失败后尝试 \n→空格归一化匹配。
    数学模式内的修改不拆分原文（避免破坏 $ 配对），仅在右栏列出。
    """
    if not corrections:
        return [{"text": paragraph, "correction": None}]

    # 查找命中，对数学模式内/外分开处理
    hits_outside = []  # 数学模式外：可拆分+内联标记
    hits_inside = []   # 数学模式内：不拆分，仅右栏列出
    found_inside_corrs = set()

    for corr in corrections:
        search_key = corr.get("original") or corr.get("location", "")
        if not search_key:
            continue
        idx = paragraph.find(search_key)
        if idx < 0:
            norm_para = paragraph.replace("\n", " ")
            norm_key = search_key.replace("\n", " ")
            idx_norm = norm_para.find(norm_key)
            if idx_norm >= 0:
                idx = _norm_pos_to_orig(paragraph, idx_norm)
        if idx >= 0:
            if _in_math(paragraph, idx):
                hits_inside.append(corr)
                found_inside_corrs.add(id(corr))
            else:
                hits_outside.append((idx, idx + len(search_key), corr))

    if not hits_outside and not hits_inside:
        return [{"text": paragraph, "correction": None}]

    # 处理数学模式外的拆分
    hits_outside.sort(key=lambda x: x[0])
    merged = []
    for start, end, corr in hits_outside:
        if merged and start < merged[-1][1]:
            continue
        merged.append((start, end, corr))

    segments = []
    pos = 0
    for start, end, corr in merged:
        if start > pos:
            segments.append({"text": paragraph[pos:start], "correction": None})
        segments.append({"text": paragraph[start:end], "correction": corr})
        pos = end
    if pos < len(paragraph):
        segments.append({"text": paragraph[pos:], "correction": None})

    # 把数学模式内的修改项附加到段落末尾（标记为"仅右栏"）
    for corr in hits_inside:
        if not segments:
            segments = [{"text": paragraph, "correction": None}]
        # 附加到第一个 segment 的段落级元数据中
        # 简化：在段落末尾添加一个虚拟 segment，text 为空，仅用于右栏
        pass  # 这些通过 para_corrections 在右栏处理

    # 返回 segments + 数学模式内的 corrections 信息
    # 用第一个 segment 存储额外的 inside-math corrections
    if segments:
        segments[0]["_math_inside_corrections"] = hits_inside

    return segments


def _norm_pos_to_orig(original: str, norm_pos: int) -> int:
    """将归一化（\n→空格）后的位置映射回原始文本位置"""
    orig_pos = 0
    norm_count = 0
    for i, ch in enumerate(original):
        if norm_count >= norm_pos:
            return i
        norm_count += 1 if ch != "\n" else 1  # \n 在 norm 中对应空格，也占一位
    return len(original)


def build_paracol_content(md_content: str, corrections: list[dict]) -> str:
    """从 Markdown 内容和修改列表构建 paracol 双栏 LaTeX 内容。"""

    corrections = corrections or []
    paragraphs = [p for p in md_content.strip().split("\n\n") if p.strip()]

    result_parts = [r"\begin{paracol}{2}", ""]

    for para in paragraphs:
        segments = _find_corrections_in_paragraph(para, corrections)
        has_correction = any(
            s.get("correction") is not None or s.get("_math_inside_corrections")
            for s in segments
        )

        if not has_correction:
            result_parts.append(_convert_images(_escape_preserve_math(para)))
            result_parts.append("")
        else:
            # 渲染左栏
            left_parts = []
            for seg in segments:
                text = seg["text"]
                corr = seg.get("correction")
                if corr is None:
                    left_parts.append(_escape_preserve_math(text))
                else:
                    ctype = corr["type"]
                    escaped = _escape_preserve_math(text)
                    if ctype == "text":
                        correction_text = corr.get("correction", "")
                        left_parts.append(r"\corrtext{" + escaped + "}{" + correction_text + "}")
                    elif ctype == "rewrite":
                        left_parts.append(r"\corrrewrite{" + escaped + "}")
                    elif ctype == "region":
                        left_parts.append(r"\corrregion{" + escaped + "}")

            result_parts.append(_convert_images("".join(left_parts)))

            # 右栏
            result_parts.append(r"\switchcolumn")
            result_parts.append("")

            para_corrections = []
            for seg in segments:
                corr = seg.get("correction")
                if corr and corr not in para_corrections:
                    para_corrections.append(corr)
                for corr_math in seg.get("_math_inside_corrections", []):
                    if corr_math not in para_corrections:
                        para_corrections.append(corr_math)

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
    """读取校对 JSON 和原始 .md，生成 .tex 文件。"""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    with open(md_path, "r", encoding="utf-8") as f:
        md_content = f.read()

    corrections = data.get("corrections", [])
    paracol_content = build_paracol_content(md_content, corrections)

    title = os.path.splitext(os.path.basename(md_path))[0]

    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        template = f.read()

    full_tex = template.replace("{{CONTENT}}", paracol_content)
    full_tex = full_tex.replace(r"\title{校对报告}", r"\title{" + title + "}")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_tex)

    return output_path
