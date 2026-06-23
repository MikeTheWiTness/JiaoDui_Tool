"""
LaTeX .tex 生成模块
读取结构化校对 JSON + 原始 .md → 生成 paracol 双栏 .tex 文件。

左栏：原文 + 编号标记（\\corrmark{文字}{编号}），右栏：编号 + 原因说明。
"""
import itertools
import json
import os
import re
import sys

_counter = itertools.count(1)

_TEMPLATE_FILE = None


def _get_template_file():
    """返回 proofread_template.tex 的绝对路径，兼容 PyInstaller 新旧版本。"""
    global _TEMPLATE_FILE
    if _TEMPLATE_FILE is not None:
        return _TEMPLATE_FILE
    # 开发模式：模块所在目录下的 templates/
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "proofread_template.tex"),
    ]
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后：
        # 旧版 (5.x) data 在 exe 同级 → exe_dir/templates/...
        # 新版 (6.x) data 在 _internal/ → exe_dir/_internal/templates/...
        exe_dir = os.path.dirname(sys.executable)
        candidates.insert(0, os.path.join(exe_dir, "_internal", "templates", "proofread_template.tex"))
        candidates.insert(0, os.path.join(exe_dir, "templates", "proofread_template.tex"))
    for p in candidates:
        if os.path.isfile(p):
            _TEMPLATE_FILE = p
            return _TEMPLATE_FILE
    # 报清楚错误
    searched = "\n  ".join(candidates)
    raise FileNotFoundError(f"找不到 proofread_template.tex，已搜索:\n  {searched}")

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


def _fix_escaped_brackets(text: str) -> str:
    r"""将非数学内容的 \[...\] 还原为 [...]（Pandoc 转义残留）。
    若方括号内包含数学符号（$、\\、^、_），则保留为显示数学模式。"""
    def _repl(m):
        inner = m.group(1)
        if re.search(r'[\$\\\^_]', inner):
            return m.group(0)  # 数学内容，保留 \[...\]
        return '[' + inner + ']'  # 纯文本，还原方括号
    return re.sub(r'\\\[([^\]]*?)\\\]', _repl, text)


def _escape_unescaped(text: str, chars: str) -> str:
    r"""转义未转义的特殊字符。已转义的（前面是反斜杠）不再重复转义。

    例：'100%' → r'100\%'，r'100\%'（已转义）→ 不变。
    避免 LLM 输出的 r'\%' 被二次转义成 r'\\%'（在 LaTeX 里 \\ 是换行，
    会破坏数学模式）。
    """
    if not chars:
        return text
    char_class = re.escape(chars)
    return re.sub(r'(?<!\\)[' + char_class + r']', lambda m: '\\' + m.group(0), text)


def _escape_preserve_math(text: str) -> str:
    parts = re.split(r"(\$\$[\s\S]*?\$\$|\$[^$]*?\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\))", text)
    result = []
    for part in parts:
        if not part:
            continue
        if part.startswith("$$"):
            # display math: $$...$$ → \[...\]
            inner = part[2:-2]
            inner = re.sub(r'([一-鿿㐀-䶿豈-﫿]+)',
                           r'\\text{\1}', inner)
            inner = inner.replace(r"\frac", r"\dfrac")
            inner = _escape_unescaped(inner, '%#')
            part = r"\[" + inner + r"\]"
        elif part.startswith(r"\["):
            # 已是 \[...\] 格式的显示数学，转义 % 和 #（LaTeX 注释/参数符）
            inner = part[2:-2]
            inner = _escape_unescaped(inner, '%#')
            part = r"\[" + inner + r"\]"
        elif part.startswith(r"\("):
            # 已是 \(...\) 格式的行内数学，转义 % 和 #
            inner = part[2:-2]
            inner = _escape_unescaped(inner, '%#')
            part = r"\(" + inner + r"\)"
        elif part.startswith("$"):
            # inline math: $...$ → \(...\)
            inner = part[1:-1]
            inner = re.sub(r'([一-鿿㐀-䶿豈-﫿]+)',
                           r'\\text{\1}', inner)
            inner = inner.replace(r"\frac", r"\dfrac")
            inner = _escape_unescaped(inner, '%#')
            part = r"\(" + inner + r"\)"
        else:
            part = _escape_text(part)
        result.append(part)
    return "".join(result)


def _newline_to_latex(text: str) -> str:
    r"""单换行 → \\\\，保护数学模式内的换行（\( 和 \[ 定界符）"""
    parts = re.split(r"(\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\))", text)
    result = []
    for part in parts:
        if not part:
            continue
        if part.startswith(r"\[") or part.startswith(r"\("):
            result.append(part)
        else:
            result.append(part.replace("\n", r"\\" + "\n"))
    return "".join(result)


def _extract_images(text: str) -> tuple[str, dict[str, str]]:
    """提取图片为占位符，返回 (处理后文本, {占位符: LaTeX代码})。

    覆盖三种语法：
    - Markdown: `![](path)` 和 `![](path){width="X" height="Y"}`
    - HTML: `<img src="path" ...>`（Pandoc 偶尔产出，URL 可能含 & 等特殊字符）
      对 HTML img，本地路径（无 ://）转为 includegraphics；
      远程 URL（http(s)://）xelatex 无法直接获取，替换为提示文字。
    """
    img_map = {}

    def _make_img_placeholder(path: str) -> str:
        key = f"IMAGEPLACEHOLDER{next(_counter)}"
        if "://" in path:
            img_map[key] = "\\\\\n\\fbox{\\parbox{0.9\\linewidth}{\\centering [远程图片省略]}}"
        else:
            img_map[key] = (
                "\\\\\n\\includegraphics[width=\\linewidth,keepaspectratio]{" + path + "}"
            )
        return key

    def _md_repl(m):
        return _make_img_placeholder(m.group(1))

    def _html_repl(m):
        path = m.group(1) or m.group(2) or m.group(3)
        return _make_img_placeholder(path)

    # ![](path){width="X" height="Y"}
    text = re.sub(
        r"!\[.*?\]\((.*?)\)\s*\{width=\"[^\"]*\"\s+height=\"[^\"]*\"\}",
        _md_repl, text,
    )
    # ![](path)
    text = re.sub(r"!\[.*?\]\((.*?)\)", _md_repl, text)
    # <img src="path" ...>  ——  匹配双引号、单引号、无引号三种形式
    text = re.sub(
        r'<img\s+[^>]*?src=(?:"([^"]*)"|\'([^\']*)\'|([^\s>]+))[^>]*?>',
        _html_repl, text,
        flags=re.IGNORECASE,
    )
    return text, img_map


def _extract_md_formatting(text: str, placeholder_map: dict[str, str]) -> str:
    """提取 Markdown 粗/斜体为占位符，替换为 LaTeX 命令"""

    def _bold_repl(m):
        key = f"FMTBOLD{next(_counter)}"
        placeholder_map[key] = r"\textbf{" + m.group(1) + "}"
        return key

    def _italic_repl(m):
        key = f"FMTIT{next(_counter)}"
        placeholder_map[key] = r"\textit{" + m.group(1) + "}"
        return key

    text = re.sub(r"\*\*(.+?)\*\*", _bold_repl, text)
    text = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", _italic_repl, text)
    return text


def _rewrite_unresolvable_images(para_content: str, available_files: set[str]) -> str:
    r"""把 \includegraphics{...} 里无法解析的路径替换为占位提示框。

    背景：LLM 校对员有时会在 marked_text 中插入虚构的图片引用
    （如 ../_resources/42761a09440b4797b4392b3b9573e036.png），拆分工具找不到
    图片时会原样保留路径。这些路径在 xelatex 编译时会触发
    "Unable to load picture or PDF file" 错误并导致 PDF 损坏。

    Args:
        para_content: build_paracol_content 的输出（含 \includegraphics{...}）
        available_files: 可用的图片文件名集合（不含路径）。凡是 \includegraphics
            引用的文件名不在此集合中的，一律替换为占位提示框。

    Returns:
        处理后的 para_content —— 所有无法解析的图片引用都被替换为
        \fbox{[图片缺失: 文件名]} 提示。
    """
    if not available_files:
        # 无可用图片 —— 所有 \includegraphics 都应替换
        pass

    def _check_includegraphics(m):
        full = m.group(0)
        path = m.group(1).strip()
        # 取文件名部分（去掉任何路径前缀）
        fname = os.path.basename(path)
        if fname in available_files:
            return full
        # 无法解析 —— 替换为占位提示框
        # 用 sanitize 后的 fname 避免特殊字符破坏 LaTeX
        safe_fname = fname.replace("_", r"\_").replace("%", r"\%").replace("#", r"\#")
        # "\\\\" 是 Python 源码 2 个反斜杠 = LaTeX 的 \\ 换行
        # "\n" 是真实换行，便于阅读 .tex 源码
        # "\fbox{...}" 是 LaTeX 命令
        return "\\\\\n\\fbox{\\parbox{0.9\\linewidth}{\\centering [图片缺失: " + safe_fname + r"]}}"

    # 匹配 \includegraphics[选项]{路径}  ——  保留选项，但替换整个命令
    return re.sub(r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}",
                  _check_includegraphics, para_content)


def _restore_placeholders(text: str, placeholder_map: dict[str, str]) -> str:
    """将所有占位符替换回 LaTeX 代码（两轮，处理嵌套占位符）"""
    for key, latex in placeholder_map.items():
        text = text.replace(key, latex)
    # 第二轮：还原嵌套在已还原值内部的占位符
    # （如 INLINEMARKER 被包在 FMTBOLD/IMG 等外层占位符的值里）
    for key, latex in placeholder_map.items():
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
    r"""检查位置 pos 是否在 \(...\) 或 \[...\] 数学模式内"""
    count = 0
    i = 0
    while i < pos:
        if text[i:i+2] == r"\[":
            count += 1; i += 2; continue
        if text[i:i+2] == r"\]":
            count -= 1; i += 2; continue
        if text[i:i+2] == r"\(":
            count += 1; i += 2; continue
        if text[i:i+2] == r"\)":
            count -= 1; i += 2; continue
        i += 1
    return count > 0


def _find_math_close(text: str, start: int) -> int:
    r"""从 start（已在数学模式内）找到配对的 \) 或 \] 闭合位置"""
    i = start
    while i < len(text):
        if text[i:i+2] == r"\)" or text[i:i+2] == r"\]":
            return i + 1
        i += 1
    return len(text)


def _md_key_to_latex(text: str) -> str:
    """将 Markdown 格式的搜索键转为 LaTeX 形式，用于在已处理内容中 fallback 搜索。"""
    # 粗体 **text** → \textbf{text}
    text = re.sub(r'\*\*(.+?)\*\*', r'\\textbf{\1}', text)
    # 斜体 *text* → \textit{text}
    text = re.sub(r'(?<!\*)\*([^*\n]+?)\*(?!\*)', r'\\textit{\1}', text)
    return text


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

        # 逐层 fallback 搜索（只标记第一处）
        idx = md_content.find(search_key)
        if idx < 0:
            norm = md_content.replace("\n", " ")
            norm_key = search_key.replace("\n", " ")
            idxn = norm.find(norm_key)
            if idxn >= 0:
                idx = _norm_pos(md_content, idxn)
        if idx < 0:
            latex_key = _md_key_to_latex(search_key)
            if latex_key != search_key:
                idx = md_content.find(latex_key)
                if idx >= 0:
                    search_key = latex_key
        if idx < 0:
            # LLM 有时会省略 $...$ 数学定界符，去掉 $ 后模糊匹配
            stripped_content = md_content.replace("$", "")
            stripped_key = search_key.replace("$", "")
            idx_s = stripped_content.find(stripped_key)
            if idx_s >= 0 and "$" in md_content:
                orig_pos = 0; stripped_pos = 0
                for ch in md_content:
                    if stripped_pos == idx_s:
                        break
                    if ch != "$":
                        stripped_pos += 1
                    orig_pos += 1
                idx = orig_pos
                search_key = stripped_key
        if idx >= 0:
            positioned.append((idx, idx + len(search_key), corr))

    positioned.sort(key=lambda x: x[0], reverse=True)

    result = md_content
    for start, end, corr in positioned:
        num = corr["num"]
        if _in_math(result, start):
            # 数学模式内：只加上标圈号（\colorbox 在数学模式内无效）
            close = _find_math_close(result, end)
            marker = r"\textsuperscript{\textcolor{red}{\redcircled{" + str(num) + r"}}}"
            result = result[:close+1] + marker + result[close+1:]
        else:
            # 文本模式：红色底色高亮 + 圈号
            result = (result[:start]
                      + r"\corrmark{" + result[start:end] + r"}{" + str(num) + r"}"
                      + result[end:])

    return result, numbered


def _format_right_entry(corr: dict) -> str:
    num = corr["num"]
    reason = corr.get("reason", "")
    corrected = corr.get("correction", "")
    ctype = corr.get("type", "text")

    # 处理 Markdown 粗/斜体
    def _fmt_md(s):
        s = re.sub(r'\*\*(.+?)\*\*', r'\\textbf{\1}', s)
        s = re.sub(r'(?<!\*)\*([^*\n]+?)\*(?!\*)', r'\\textit{\1}', s)
        return s
    reason = _fmt_md(reason)
    corrected = _fmt_md(corrected)

    reason = _escape_preserve_math(reason)
    corrected = _escape_preserve_math(corrected)
    cc = r"\redcircled{" + str(num) + r"}"
    corrected = _fix_missing_chars(corrected)
    reason = _fix_missing_chars(reason)
    reason_part = f" \\\\ 修改原因：{reason}" if reason else ""
    if ctype == "text":
        return f"{cc} 改为：{corrected}{reason_part}"
    elif ctype == "rewrite":
        return f"{cc} 重写为：{corrected}{reason_part}"
    elif ctype == "region":
        return f"{cc} 修改：{corrected}{reason_part}"
    return f"{cc} {reason}"


def _merge_split_math_blocks(text: str) -> str:
    r"""修复被内联标记切开的 $ 数学块，特别是 \left...\right 配对分裂。

    当 LLM 在 $\frac{d}{dx}\left($【7|$...$|$...$】$\right)$ 中插入
    $...$ 包裹的标记时，剥离 $ 后变成：
      $\frac{d}{dx}\left($<stripped_orig>KEY$\right)$
    其中 $ 块 1 有空闲 \left（无匹配 \right），$ 块 2 有空闲 \right
    （无匹配 \left）。需要合并两个相邻 $ 块为一个。
    """
    def _has_unpaired_left(s):
        return len(re.findall(r'\\left[({\[\|.]', s)) > len(re.findall(r'\\right[)\]}\|.]', s))

    def _has_unpaired_right(s):
        return len(re.findall(r'\\right[)\]}\|.]', s)) > len(re.findall(r'\\left[({\[\|.]', s))

    # 匹配相邻的 $...$$...$ 块（两个 $ 块中间无实质内容）
    # 第二个 $ 可能紧接在第一个 $ 之后，或中间有空白/占位符
    pattern = re.compile(r'(\$[^$]+\$)\s*(\$[^$]+\$)')

    def _merge_repl(m):
        left_block = m.group(1)
        right_block = m.group(2)
        left_inner = left_block[1:-1]
        right_inner = right_block[1:-1]
        if _has_unpaired_left(left_inner) and _has_unpaired_right(right_inner):
            # 合并：去掉中间的 $$
            return "$" + left_inner + right_inner + "$"
        return m.group(0)

    # 多轮替换直到没有更多可合并的
    prev = None
    while prev != text:
        prev = text
        text = pattern.sub(_merge_repl, text)
    return text

# 数字 → 圈号 Unicode 字符映射（1-20）
_CIRCLED_NUMS = '①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳'


def _circled_char(n: int) -> str:
    """1 → ①, 2 → ②, ..."""
    if 1 <= n <= len(_CIRCLED_NUMS):
        return _CIRCLED_NUMS[n - 1]
    return str(n)


_INLINE_MARKER_RE = re.compile(r'【([\d①-⑳]+)\|([^|]*?)\|([^】]*?)】')


def _parse_marker_num(s: str) -> int:
    """'①' → 1, '1' → 1"""
    code = ord(s[0])
    if 0x2460 <= code <= 0x2473:
        return code - 0x2460 + 1
    return int(s)


def _process_inline_markers(md_text: str, corrections: list[dict],
                            placeholder_map: dict[str, str]) -> tuple[str, list[dict]]:
    """处理新格式的 【N原文|改为】 内联标记。

    标记中的 LaTeX 替换为占位符（避免后续 escaping 破坏），
    返回 (已替换占位符的文本, 编号修改列表)。
    """
    reason_map = {}
    for c in (corrections or []):
        n = c.get("num", 0)
        if n:
            reason_map[n] = c.get("reason", "")

    inline_corrections = []
    seen = set()

    def _repl(m):
        num = _parse_marker_num(m.group(1))
        orig = m.group(2)
        corr = m.group(3)
        if num not in seen:
            seen.add(num)
            inline_corrections.append({
                "num": num,
                "type": "text",
                "original": orig,
                "correction": corr,
                "reason": reason_map.get(num, ""),
            })

        # 剥离 $ 定界符。处理策略取决于标记位置：
        # - 标记在 $...$ 内 → 裸数学内容 + 上标圈号（数学模式内不能放 \colorbox）
        # - 标记在文本中 → \corrmark{\(inner\)}{N} 红色底色高亮 + 圈号
        if orig.startswith("$") and orig.endswith("$") and len(orig) > 2:
            inner = orig[1:-1]
            before_marker = md_text[:m.start()]
            in_math = (before_marker.count("$") % 2 == 1)
            if in_math:
                # 数学模式内：裸内容 + 上标圈号（保持现有行为）
                math_key = f"MATHPLACEHOLDER{num}"
                placeholder_map[math_key] = inner
                key = f"INLINEMARKER{num}"
                placeholder_map[key] = (
                    r"\textsuperscript{\textcolor{red}{\redcircled{"
                    + str(num) + r"}}}"
                )
                return math_key + key
            else:
                # 文本模式：红色底色高亮 + 圈号
                key = f"CORRMARK{num}"
                placeholder_map[key] = (
                    r"\corrmark{" + r"\(" + inner + r"\)" + r"}"
                    + r"{" + str(num) + r"}"
                )
                return key

        if orig.startswith("$$") and orig.endswith("$$") and len(orig) > 4:
            inner = orig[2:-2]
            before_marker = md_text[:m.start()]
            in_math = (before_marker.count("$$") % 2 == 1)
            if in_math:
                math_key = f"MATHPLACEHOLDER{num}"
                placeholder_map[math_key] = inner
                key = f"INLINEMARKER{num}"
                placeholder_map[key] = (
                    r"\textsuperscript{\textcolor{red}{\redcircled{"
                    + str(num) + r"}}}"
                )
                return math_key + key
            else:
                key = f"CORRMARK{num}"
                placeholder_map[key] = (
                    r"\corrmark{" + r"\[" + inner + r"\]" + r"}"
                    + r"{" + str(num) + r"}"
                )
                return key

        # 纯文本标记（无 $ 包裹）：红色底色高亮 + 圈号
        key = f"CORRMARK{num}"
        placeholder_map[key] = (
            r"\corrmark{" + orig + r"}{" + str(num) + r"}"
        )
        return key

    # 第一步：预处理——合并被 $...$ 包裹标记切开的相邻 $ 块。
    # 模式：$<content1>$【N|$orig$|$corr$】$<content2>$
    # 替换为：$<content1><orig_stripped>KEY<content2>$
    # 这样 \left 和 \right 就不会被分到不同的 $ 块中。
    def _pre_merge_dollar_markers(text):
        def _merge_repl(m):
            before = m.group(1)           # $<content1>$
            after = m.group(6)            # $<content2>$  (group 2-5 are inline marker's nested groups)
            marker = m.group(2)           # 【N|...|...】
            # 解析标记内容
            mm = _INLINE_MARKER_RE.match(marker)
            if not mm:
                return m.group(0)
            num = _parse_marker_num(mm.group(1))
            orig = mm.group(2)
            corr = mm.group(3)
            if num not in seen:
                seen.add(num)
                inline_corrections.append({
                    "num": num,
                    "type": "text",
                    "original": orig,
                    "correction": corr,
                    "reason": reason_map.get(num, ""),
                })
            key = f"INLINEMARKER{num}"
            placeholder_map[key] = (
                r"\textsuperscript{\textcolor{red}{\redcircled{"
                + str(num) + r"}}}"
            )
            # 剥离 orig 的 $ 定界符（已在合并后的 $ 块内，不需要 \(...\) 包裹）
            inner = orig
            if orig.startswith("$$") and orig.endswith("$$") and len(orig) > 4:
                inner = orig[2:-2]
            elif orig.startswith("$") and orig.endswith("$") and len(orig) > 2:
                inner = orig[1:-1]
            # 合并前后的 $ 块：去掉中间两个 $，保留前后的 $
            return before[:-1] + inner + key + after[1:]

        # 匹配：$<content>$【N|...|...】$<content>$
        pre_pattern = re.compile(
            r'(\$[^$]+\$)'
            r'\s*(' + _INLINE_MARKER_RE.pattern + r')'
            r'\s*(\$[^$]+\$)'
        )
        return pre_pattern.sub(_merge_repl, text)

    processed = _pre_merge_dollar_markers(md_text)

    # 第二步：处理剩余的普通内联标记
    processed = _INLINE_MARKER_RE.sub(_repl, processed)
    inline_corrections.sort(key=lambda x: x["num"])

    # 修复被 $ 剥离后残留的 split-math 问题：\left 和 \right 落在不同 $ 块
    # 例：$\frac{d}{dx}\left($ 剥离后 → $\frac{d}{dx}\left(<inner>$KEY$\right)$
    # 需要把中间的 $KEY$ 两边 $ 去掉，让 \left 和 \right 留在同一 $ 块
    processed = _merge_split_math_blocks(processed)

    return processed, inline_corrections


def _fix_missing_chars(text: str) -> str:
    """替换 SimSun 不包含的常见符号，用字体切换包裹。"""
    # 先剥离已有的 \fallbacksymbols 包裹，避免双重嵌套
    text = re.sub(r'\{\\fallbacksymbols ([^}]*)\}', r'\1', text)
    # 星号 ★☆（U+2605 / U+2606）
    text = text.replace('★', r'{\fallbacksymbols ★}')
    text = text.replace('☆', r'{\fallbacksymbols ☆}')
    # 圈号数字 ①-⑳（U+2460–U+2473）
    for ch in '①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳':
        text = text.replace(ch, r'{\fallbacksymbols ' + ch + '}')
    # 省略号 …（U+2026）
    if '…' in text:
        text = text.replace('…', r'{\fallbacksymbols …}')
    return text


def build_paracol_content(md_content: str, corrections: list[dict],
                          tool_calls: list[dict] | None = None) -> str:
    corrections = corrections or []

    md_processed, placeholder_map = _extract_images(md_content)

    # 检测新格式：内联标记 【N原文|改为】（必须在格式化之前）
    has_inline = bool(_INLINE_MARKER_RE.search(md_processed))
    if has_inline:
        md_processed, numbered = _process_inline_markers(md_processed, corrections, placeholder_map)

    md_processed = _extract_md_formatting(md_processed, placeholder_map)
    md_processed = re.sub(r'^#{1,4}\s+(.+)', r'\\textbf{\1}', md_processed, flags=re.MULTILINE)

    # 修复 Pandoc 转义残留：非数学内容的 \[...\] → [...]
    md_processed = _fix_escaped_brackets(md_processed)

    escaped = _escape_preserve_math(md_processed)
    escaped = _restore_placeholders(escaped, placeholder_map)
    # 缺失字符用回退字体包裹（必须在 escaping 之后，避免 \fallbacksymbols 命令被转义）
    escaped = _fix_missing_chars(escaped)
    escaped = escaped.replace('"', r'{\fallbacksymbols "}')
    # 单换行 → LaTeX 换行
    escaped = _newline_to_latex(escaped)

    if not has_inline:
        marked, numbered = _apply_markers(escaped, corrections)
    else:
        marked = escaped

    lines = [r"\begin{paracol}{2}", ""]
    lines.append(marked)
    lines.append(r"\switchcolumn")
    lines.append("")

    if numbered:
        for corr in numbered:
            lines.append(r"\correctionbox{" + _format_right_entry(corr) + "}")
            lines.append(r"\medskip")
            lines.append("")

    # 工具调用记录
    if tool_calls:
        tc_lines = [r"\textbf{{\fallbacksymbols 🔧} 工具调用记录：}", ""]
        for tc in tool_calls:
            tname = tc.get("tool", "?").replace("_", r"\_")
            args_str = _escape_text(json.dumps(tc.get("args", {}), ensure_ascii=False))
            result_str = _escape_text(str(tc.get("result", ""))[:100])
            tc_lines.append(
                rf"\textbullet\ \texttt{{{tname}}} "
                rf"({args_str}) "
                rf"$\rightarrow$ {result_str}"
            )
        tc_block = r"\par ".join(tc_lines)
        lines.append(r"\correctionbox{" + tc_block + "}")
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

    with open(_get_template_file(), "r", encoding="utf-8") as f:
        template = f.read()

    full_tex = template.replace("{{CONTENT}}", paracol_content)
    full_tex = full_tex.replace(r"\title{校对报告}", r"\title{" + title.replace("_", r"\_") + "}")

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

    def _sort_key(entry):
        nums = re.findall(r'\d+', entry)
        return (int(nums[0]) if nums else 9999, entry)

    subdirs = []
    for entry in sorted(os.listdir(lecture_dir), key=_sort_key):
        if entry in ("知识",):  # 跳过知识
            continue
        full = os.path.join(lecture_dir, entry)
        if os.path.isdir(full) and not entry.startswith("_"):
            subdirs.append(full)

    if not subdirs:
        return None

    # 逐个构建 paracol 内容，每个题目的图片使用独立子目录
    sections = []
    all_images = {}  # {section_title: {filename: source_path}}
    for subdir in subdirs:
        json_path = os.path.join(subdir, "_校对数据.json")
        md_path = _find_md_file(subdir)
        if not os.path.isfile(json_path) or not md_path:
            continue

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        marked_text = data.get("marked_text", "")
        if marked_text:
            md_content = marked_text.replace(chr(92) + 'n', '\n')
        else:
            with open(md_path, "r", encoding="utf-8") as f:
                md_content = f.read()

        corrections = data.get("corrections", [])
        tool_calls = data.get("tool_calls", [])
        section_title = _get_section_name(subdir)
        para_content = build_paracol_content(md_content, corrections, tool_calls)

        # 将图片路径从 ./images/ 改为 ./{题目名}/images/ 以避免跨题目冲突
        img_dir = os.path.join(subdir, "images")
        available_files: set[str] = set()
        if os.path.isdir(img_dir):
            sec_img_prefix = f"./{section_title}/images/"
            para_content = para_content.replace("{./images/", "{" + sec_img_prefix)
            all_images[section_title] = {}
            for fname in os.listdir(img_dir):
                all_images[section_title][fname] = os.path.join(img_dir, fname)
                available_files.add(fname)

        # 把无法解析的图片引用（如 LLM 虚构的 ../_resources/xxx.png）
        # 替换为占位提示框，避免 xelatex 加载失败导致 PDF 损坏
        para_content = _rewrite_unresolvable_images(para_content, available_files)

        sections.append(f"\\section*{{{section_title}}}\n{para_content}")

    if not sections:
        return None

    combined = ("\n\n" + chr(92) + "newpage\n\n").join(sections)
    lecture_name = os.path.basename(lecture_dir.rstrip("/\\"))

    with open(_get_template_file(), "r", encoding="utf-8") as f:
        template = f.read()

    full_tex = template.replace("{{CONTENT}}", combined)
    full_tex = full_tex.replace(r"\title{校对报告}", r"\title{" + lecture_name.replace("_", r"\_") + "}")

    if pdf_output_dir is None:
        pdf_output_dir = lecture_dir
    os.makedirs(pdf_output_dir, exist_ok=True)

    safe_name = lecture_name.replace(" ", "_")
    tex_path = os.path.join(pdf_output_dir, f"{safe_name}.tex")

    with open(tex_path, "w", encoding="utf-8") as f:
        f.write(full_tex)

    try:
        from pdf_compiler import compile_to_pdf
        # 图片映射传给编译器，由它复制到临时目录
        pdf_path = compile_to_pdf(tex_path, output_dir=pdf_output_dir, images_map=all_images)
        return pdf_path
    except Exception as e:
        # 编译失败时，删除可能残留的 PDF（xelatex 在崩溃前可能已写出残缺 PDF）
        # 避免用户误以为 PDF 生成成功
        partial_pdf = os.path.join(pdf_output_dir, f"{safe_name}.pdf")
        if os.path.isfile(partial_pdf):
            try:
                os.remove(partial_pdf)
            except OSError:
                pass
        # 重新抛出，让调用方决定如何向用户展示错误
        raise RuntimeError(f"LaTeX 编译失败：{e}") from e


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
    except Exception as e:
        partial_pdf = os.path.join(pdf_output_dir, f"{q_name}.pdf")
        if os.path.isfile(partial_pdf):
            try:
                os.remove(partial_pdf)
            except OSError:
                pass
        raise RuntimeError(f"LaTeX 编译失败：{e}") from e
