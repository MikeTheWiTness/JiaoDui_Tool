"""
LaTeX .tex 生成模块
读取结构化校对 JSON + 原始 .md → 生成 paracol 双栏 .tex 文件。

左栏：原文 + 编号标记（\corrmark{文字}{编号}），右栏：编号 + 原因说明。
"""
import json
import os
import re

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
TEMPLATE_FILE = os.path.join(TEMPLATE_DIR, "proofread_template.tex")

_LATEX_SPECIAL = [
    ("\\", r"\textbackslash "),
    ("&", r"\&"),
    ("%", r"\%"),
    ("$", r"\$"),
    ("_", r"\_"),
    ("{", r"\{"),
    ("}", r"\}"),
    ("~", r"\textasciitilde "),
    ("^", r"\textasciicircum "),
]


def _escape_text(text: str) -> str:
    for char, replacement in _LATEX_SPECIAL:
        text = text.replace(char, replacement)
    return text


def _escape_preserve_math(text: str) -> str:
    parts = re.split(r"(\$\$[\s\S]*?\$\$|\$[^$]*?\$)", text)
    result = []
    for part in parts:
        if not part:
            continue
        if part.startswith("$"):
            # 数学模式内：CJK 字符用 \text{} 包裹
            part = re.sub(r'([一-鿿㐀-䶿豈-﫿]+)',
                          r'\\text{\1}', part)
        else:
            part = _escape_text(part)
        result.append(part)
    return "".join(result)


def _newline_to_latex(text: str) -> str:
    """单换行 → \\\\，保护数学模式内的换行"""
    parts = re.split(r"(\$\$[\s\S]*?\$\$|\$[^$]*?\$)", text)
    result = []
    for part in parts:
        if not part:
            continue
        if part.startswith("$"):
            result.append(part)
        else:
            result.append(part.replace("\n", r"\\" + "\n"))
    return "".join(result)


_IMG_COUNTER = 0


def _extract_images(text: str) -> tuple[str, dict[str, str]]:
    """提取 Markdown 图片为占位符，返回 (处理后文本, {占位符: LaTeX代码})"""
    global _IMG_COUNTER
    img_map = {}

    def _repl(m):
        global _IMG_COUNTER
        _IMG_COUNTER += 1
        key = f"IMAGEPLACEHOLDER{_IMG_COUNTER}"
        path = m.group(1)
        img_map[key] = (
            "\\\\\n\\includegraphics[width=\\linewidth,keepaspectratio]{" + path + "}"
        )
        return key

    # ![](path){width="X" height="Y"}
    text = re.sub(
        r"!\[.*?\]\((.*?)\)\s*\{width=\"[^\"]*\"\s+height=\"[^\"]*\"\}",
        _repl, text,
    )
    # ![](path)
    text = re.sub(r"!\[.*?\]\((.*?)\)", _repl, text)
    return text, img_map


def _restore_images(text: str, img_map: dict[str, str]) -> str:
    """将占位符替换回 LaTeX 图片代码"""
    for key, latex in img_map.items():
        text = text.replace(key, latex)
    return text


def _norm_pos(original: str, norm_pos: int) -> int:
    count = 0
    for i, ch in enumerate(original):
        if count >= norm_pos:
            return i
        count += 1
    return len(original)


def _in_math(text: str, pos: int) -> bool:
    count = 0
    i = 0
    while i < pos:
        if text[i:i+2] == "$$":
            count += 1
            i += 2
            continue
        if text[i] == "$":
            count += 1
        i += 1
    return count % 2 == 1


def _find_math_close(text: str, start: int) -> int:
    """从 start（已在数学模式内）找到配对的 $ 闭合位置"""
    i = start
    while i < len(text):
        if text[i] == "$" and text[i+1:i+2] != "$":
            return i
        if text[i:i+2] == "$$":
            close = text.find("$$", i+2)
            return close + 2 if close >= 0 else i
        i += 1
    return len(text)


def _apply_markers(md_content: str, corrections: list[dict]) -> tuple[str, list[dict]]:
    """在原文错误位置后插入 \textsuperscript{\textcircled{N}} 标记。"""
    if not corrections:
        return md_content, []

    numbered = []
    for i, corr in enumerate(corrections, 1):
        numbered.append({**corr, "num": i})

    positioned = []
    for corr in numbered:
        search_key = corr.get("original") or corr.get("location", "")
        if not search_key:
            continue
        idx = md_content.find(search_key)
        if idx < 0:
            norm = md_content.replace("\n", " ")
            norm_key = search_key.replace("\n", " ")
            idxn = norm.find(norm_key)
            if idxn >= 0:
                idx = _norm_pos(md_content, idxn)
        if idx >= 0:
            positioned.append((idx, idx + len(search_key), corr))

    positioned.sort(key=lambda x: x[0], reverse=True)

    result = md_content
    for start, end, corr in positioned:
        num = corr["num"]
        marker = r"\textsuperscript{\textcolor{red}{\textcircled{" + str(num) + "}}}"
        if _in_math(result, start):
            close = _find_math_close(result, end)
            result = result[:close+1] + marker + result[close+1:]
        else:
            result = result[:end] + marker + result[end:]

    return result, numbered


def _format_right_entry(corr: dict) -> str:
    num = corr["num"]
    reason = _escape_preserve_math(corr.get("reason", ""))
    return f"\\textcircled{{{num}}} {reason}"


def build_paracol_content(md_content: str, corrections: list[dict]) -> str:
    corrections = corrections or []

    # 先提取图片为占位符，转义后再替换（避免 LaTeX 命令被 escape）
    md_with_placeholders, img_map = _extract_images(md_content)
    escaped = _escape_preserve_math(md_with_placeholders)
    escaped = _restore_images(escaped, img_map)
    # Markdown 标题 # → 粗体文字（匹配行首 # 后跟空格、文字，到行尾）
    escaped = re.sub(r'^#{1,4}\s+(.+)', r'\\textbf{\1}', escaped, flags=re.MULTILINE)
    # 单换行 → LaTeX 换行
    escaped = _newline_to_latex(escaped)

    marked, numbered = _apply_markers(escaped, corrections)

    lines = [r"\begin{paracol}{2}", ""]
    lines.append(marked)
    lines.append(r"\switchcolumn")
    lines.append("")

    if numbered:
        for corr in numbered:
            lines.append(r"\correctionbox{" + _format_right_entry(corr) + "}")
            lines.append(r"\medskip")
            lines.append("")

    lines.append(r"\switchcolumn*")
    lines.append("")
    lines.append(r"\end{paracol}")
    return "\n".join(lines)


def generate_tex(json_path: str, md_path: str, output_path: str) -> str:
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


def _find_md_file(subdir: str) -> str | None:
    """在子目录中查找 .md 文件（非 _ 开头的报告文件）"""
    md_files = [f for f in os.listdir(subdir)
                if f.endswith(".md") and not f.startswith("_")]
    return os.path.join(subdir, md_files[0]) if md_files else None


def _get_section_name(q_dir: str) -> str:
    """从目录名提取用于显示的名称"""
    name = os.path.basename(q_dir.rstrip("/\\"))
    return name


def generate_combined_pdf(lecture_dir: str, pdf_output_dir: str | None = None) -> str | None:
    """扫描讲义目录下所有题目/知识子目录，生成一份汇总 PDF。

    每个子目录生成独立的 paracol 双栏，\newpage 分隔。
    自动汇总各子目录的图片到统一 images/ 目录。
    """
    if not os.path.isdir(lecture_dir):
        return None

    subdirs = []
    for entry in sorted(os.listdir(lecture_dir)):
        full = os.path.join(lecture_dir, entry)
        if os.path.isdir(full) and not entry.startswith("_"):
            subdirs.append(full)

    if not subdirs:
        return None

    # 逐个构建 paracol 内容，同时收集图片
    sections = []
    all_images = {}  # {filename: source_path}
    for subdir in subdirs:
        json_path = os.path.join(subdir, "_校对数据.json")
        md_path = _find_md_file(subdir)
        if not os.path.isfile(json_path) or not md_path:
            continue

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        with open(md_path, "r", encoding="utf-8") as f:
            md_content = f.read()

        corrections = data.get("corrections", [])
        section_title = _get_section_name(subdir)
        para_content = build_paracol_content(md_content, corrections)

        sections.append(f"\\section*{{{section_title}}}\n{para_content}")

        # 收集该子目录的图片
        img_dir = os.path.join(subdir, "images")
        if os.path.isdir(img_dir):
            for fname in os.listdir(img_dir):
                all_images[fname] = os.path.join(img_dir, fname)

    if not sections:
        return None

    combined = "\n\n\\newpage\n\n".join(sections)
    lecture_name = os.path.basename(lecture_dir.rstrip("/\\"))

    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        template = f.read()

    full_tex = template.replace("{{CONTENT}}", combined)
    full_tex = full_tex.replace(r"\title{校对报告}", r"\title{" + lecture_name + "}")

    if pdf_output_dir is None:
        pdf_output_dir = lecture_dir
    os.makedirs(pdf_output_dir, exist_ok=True)

    # 汇总图片到统一的 images/ 目录
    if all_images:
        unified_img = os.path.join(pdf_output_dir, "images")
        os.makedirs(unified_img, exist_ok=True)
        for fname, src in all_images.items():
            import shutil
            shutil.copy2(src, os.path.join(unified_img, fname))

    safe_name = lecture_name.replace(" ", "_")
    tex_path = os.path.join(pdf_output_dir, f"{safe_name}.tex")

    with open(tex_path, "w", encoding="utf-8") as f:
        f.write(full_tex)

    try:
        from pdf_compiler import compile_to_pdf
        pdf_path = compile_to_pdf(tex_path, output_dir=pdf_output_dir)
        return pdf_path
    except Exception:
        return None


def generate_pdf_for_question(q_dir: str, pdf_output_dir: str | None = None) -> str | None:
    """从单个题目目录生成校对 PDF（保留用于单题调试）。"""
    json_path = os.path.join(q_dir, "_校对数据.json")
    if not os.path.isfile(json_path):
        return None

    md_path = _find_md_file(q_dir)
    if not md_path:
        return None

    q_name = os.path.basename(q_dir.rstrip("/\\"))
    if pdf_output_dir is None:
        pdf_output_dir = q_dir

    os.makedirs(pdf_output_dir, exist_ok=True)
    tex_path = os.path.join(pdf_output_dir, f"{q_name}.tex")

    try:
        from pdf_compiler import compile_to_pdf
        generate_tex(json_path, md_path, tex_path)
        pdf_path = compile_to_pdf(tex_path, output_dir=pdf_output_dir)
        return pdf_path
    except Exception:
        return None
