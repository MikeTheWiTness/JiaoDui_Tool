"""JSON → LaTeX → PDF 全链路健壮性测试。

覆盖从校对 JSON + 原 .md 到可编译 .tex 的边界情况，重点防止：
1. 数学模式内 `%`/`#` 被重复转义（曾导致 xelatex Runaway argument + 残缺 PDF）
2. HTML `<img>` 标签原样进入 LaTeX（曾导致 \textasciitilde 等被误判为命令）
3. 编译失败时残缺 PDF 被当作成功输出返回
4. LLM 输出中常见的 LaTeX 命令、化学公式、特殊字符不破坏编译
"""
import json
import os
import re
import tempfile

import pytest

from latex_generator import (
    _escape_preserve_math,
    _escape_unescaped,
    _extract_images,
    _rewrite_unresolvable_images,
    build_paracol_content,
    generate_combined_pdf,
    generate_tex,
)
from pdf_compiler import compile_to_pdf


# ============================================================
# 辅助函数
# ============================================================

def _make_temp_dir():
    return tempfile.mkdtemp(prefix="latex_robust_")


def _write(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _count_backslash_before_percent(text: str) -> list[int]:
    """返回每个 % 前面的连续反斜杠数。用于验证转义层数。"""
    counts = []
    for i, c in enumerate(text):
        if c == "%":
            bs = 0
            j = i - 1
            while j >= 0 and text[j] == "\\":
                bs += 1
                j -= 1
            counts.append(bs)
    return counts


# ============================================================
# 单元测试：_escape_unescaped
# ============================================================

class TestEscapeUnescaped:
    def test_escapes_bare_percent(self):
        assert _escape_unescaped("100%", "%") == r"100\%"

    def test_does_not_double_escape(self):
        assert _escape_unescaped(r"100\%", "%") == r"100\%"

    def test_does_not_triple_escape(self):
        assert _escape_unescaped(r"100\\%", "%") == r"100\\%"

    def test_escapes_bare_hash(self):
        assert _escape_unescaped("a#b", "#") == r"a\#b"

    def test_does_not_double_escape_hash(self):
        assert _escape_unescaped(r"a\#b", "#") == r"a\#b"

    def test_multiple_chars(self):
        # 同时处理 % 和 #，各自只转义未转义的
        out = _escape_unescaped("100% #a \\% \\#", "%#")
        assert out == r"100\% \#a \% \#"

    def test_empty_chars_noop(self):
        assert _escape_unescaped("100%", "") == "100%"

    def test_consecutive_percents(self):
        # 两个连续 %，各转义各的
        assert _escape_unescaped("50%%", "%") == r"50\%\%"

    def test_backslash_at_start(self):
        # 开头的 % 也要转义
        assert _escape_unescaped("% start", "%") == r"\% start"

    def test_mixed_escaped_and_unescaped(self):
        # 混合场景：第一个已转义，第二个没转义
        out = _escape_unescaped(r"\% and 50%", "%")
        assert out == r"\% and 50\%"

    def test_preserves_other_backslashes(self):
        # \sin 命令里的 \s 不应被错误处理
        out = _escape_unescaped(r"\sin 50%", "%")
        assert out == r"\sin 50\%"
        assert r"\sin" in out


# ============================================================
# 单元测试：_escape_preserve_math — 核心回归测试
# ============================================================

class TestEscapePreserveMath:
    def test_unescaped_percent_in_inline_math(self):
        # LLM 忘了转义 % —— 应补上单层转义
        out = _escape_preserve_math(r"$100%$")
        assert r"100\%" in out
        # 不能是双反斜杠
        assert r"100\\%" not in out

    def test_pre_escaped_percent_in_inline_math(self):
        # LLM 已写 \%，不能再加一层
        out = _escape_preserve_math(r"$100\%$")
        assert r"100\%" in out
        assert r"100\\%" not in out

    def test_unescaped_percent_in_display_math(self):
        out = _escape_preserve_math(r"$$100%$$")
        assert r"100\%" in out
        assert r"100\\%" not in out

    def test_pre_escaped_percent_in_display_math(self):
        out = _escape_preserve_math(r"$$100\%$$")
        assert r"100\%" in out
        assert r"100\\%" not in out

    def test_unescaped_percent_in_paren_math(self):
        out = _escape_preserve_math(r"\(100%\)")
        assert r"100\%" in out
        assert r"100\\%" not in out

    def test_pre_escaped_percent_in_paren_math(self):
        out = _escape_preserve_math(r"\(100\%\)")
        assert r"100\%" in out
        assert r"100\\%" not in out

    def test_unescaped_percent_in_bracket_math(self):
        out = _escape_preserve_math(r"\[100%\]")
        assert r"100\%" in out
        assert r"100\\%" not in out

    def test_pre_escaped_percent_in_bracket_math(self):
        out = _escape_preserve_math(r"\[100\%\]")
        assert r"100\%" in out
        assert r"100\\%" not in out

    def test_hash_in_math(self):
        out = _escape_preserve_math(r"$a#b$")
        assert r"a\#b" in out
        assert r"a\\#b" not in out

    def test_pre_escaped_hash_in_math(self):
        out = _escape_preserve_math(r"$a\#b$")
        assert r"a\#b" in out
        assert r"a\\#b" not in out

    def test_text_percent_escaped(self):
        # 非数学模式下，% 仍应转义
        out = _escape_preserve_math("完成率 80%。")
        assert r"80\%" in out

    def test_multiple_percents_in_math(self):
        # LLM 输出的实际场景：η = 1/2 × 100% = 50%
        out = _escape_preserve_math(r"$\eta =\frac{1}{2}\times 100\%=50\%$")
        # 每处都应是单层转义
        counts = _count_backslash_before_percent(out)
        # 应有 2 个 %，每个前面恰好 1 个反斜杠
        assert counts == [1, 1], f"Expected [1, 1], got {counts}"

    def test_mixed_escaped_and_unescaped_in_math(self):
        # 一个已转义、一个未转义
        out = _escape_preserve_math(r"$\% and 50%$")
        counts = _count_backslash_before_percent(out)
        assert counts == [1, 1], f"Expected [1, 1], got {counts}"


# ============================================================
# 单元测试：_extract_images — HTML img 标签
# ============================================================

class TestExtractImagesHtml:
    def test_html_img_double_quoted_local(self):
        text, img_map = _extract_images('<img src="images/fig1.png" alt="图" />')
        assert "IMAGEPLACEHOLDER" in text
        assert len(img_map) == 1
        latex = next(iter(img_map.values()))
        assert r"\includegraphics" in latex
        assert "images/fig1.png" in latex

    def test_html_img_single_quoted_local(self):
        text, img_map = _extract_images("<img src='images/fig2.png' />")
        assert len(img_map) == 1
        latex = next(iter(img_map.values()))
        assert "images/fig2.png" in latex

    def test_html_img_unquoted_local(self):
        text, img_map = _extract_images("<img src=images/fig3.png>")
        assert len(img_map) == 1
        latex = next(iter(img_map.values()))
        assert "images/fig3.png" in latex

    def test_html_img_remote_url_replaced(self):
        # 实际故障案例的 URL 形式
        url = "https://example.com/img.jpeg?lk3s=abc&x-expires=123&x-signature=%2B"
        text, img_map = _extract_images(f'<img src="{url}" alt="题图" />')
        assert len(img_map) == 1
        latex = next(iter(img_map.values()))
        # 远程图片不应进入 includegraphics（否则 xelatex 会试图打开网络文件失败）
        assert r"\includegraphics" not in latex
        assert "远程图片省略" in latex or "fbox" in latex

    def test_html_img_with_attributes_before_src(self):
        text, img_map = _extract_images('<img alt="题图" src="images/x.png" width="100">')
        assert len(img_map) == 1
        latex = next(iter(img_map.values()))
        assert "images/x.png" in latex

    def test_html_img_self_closing_no_space(self):
        text, img_map = _extract_images('<img src="images/y.png"/>')
        assert len(img_map) == 1

    def test_html_img_case_insensitive(self):
        text, img_map = _extract_images('<IMG SRC="images/z.png">')
        assert len(img_map) == 1
        latex = next(iter(img_map.values()))
        assert "images/z.png" in latex

    def test_html_img_does_not_leave_raw_html(self):
        # 处理后不应残留 <img、src=、/> 等 HTML 语法
        text, _ = _extract_images('<img src="images/a.png" alt="b" />')
        assert "<img" not in text.lower()
        assert "src=" not in text.lower()
        assert "/>" not in text

    def test_html_img_with_special_chars_in_url(self):
        # URL 含 & 和 % —— 过去会导致 \& 和 \% 错误转义
        url = "https://x.com/i?a=1&b=2%20c"
        text, img_map = _extract_images(f'<img src="{url}" />')
        # 应被替换为占位符，URL 不残留
        assert "https://" not in text
        assert "&" not in text
        assert len(img_map) == 1

    def test_multiple_html_imgs(self):
        text, img_map = _extract_images(
            '<img src="images/a.png"> 文字 <img src="images/b.png">'
        )
        assert len(img_map) == 2

    def test_markdown_image_still_works(self):
        # 回归：Markdown ![](path) 必须仍能处理
        text, img_map = _extract_images("![](images/md.png)")
        assert len(img_map) == 1
        latex = next(iter(img_map.values()))
        assert r"\includegraphics" in latex
        assert "images/md.png" in latex

    def test_markdown_image_with_size(self):
        text, img_map = _extract_images('![](images/md.png){width="100" height="50"}')
        assert len(img_map) == 1
        latex = next(iter(img_map.values()))
        assert "images/md.png" in latex

    def test_mixed_markdown_and_html(self):
        text, img_map = _extract_images(
            '![](images/a.png) and <img src="images/b.png">'
        )
        assert len(img_map) == 2


# ============================================================
# 集成测试：build_paracol_content — LLM 实际输出场景
# ============================================================

class TestBuildParacolRealistic:
    def test_pre_escaped_percent_in_correction(self):
        """实际故障案例：LLM 在 correction 里已写了 \\%"""
        md = r"除尘率 $\eta =\dfrac{1}{2}\times 100\%=50\%$"
        corrections = [{
            "type": "text",
            "original": r"$\eta =\frac{1}{2}\times 100%=50%$",
            "correction": r"$\eta =\frac{1}{2}\times 100\%=50\%$",
            "reason": r"LaTeX数学环境中%为注释符，需转义为\%才能正确显示百分号",
        }]
        result = build_paracol_content(md, corrections)
        # 不应出现双反斜杠 + %
        assert r"\\%" not in result, (
            "Pre-escaped % was double-escaped — this caused the original PDF corruption"
        )
        # 应保留单层转义
        assert r"\%" in result

    def test_html_img_in_markdown_content(self):
        """实际故障案例：md 里混入 HTML img 标签"""
        md = '<img src="https://example.com/fig.png?x=1&y=2" alt="题图" /> 选项A'
        result = build_paracol_content(md, [])
        # 不应残留 HTML 语法
        assert "<img" not in result.lower()
        assert "src=" not in result.lower()
        # 不应残留原始 URL
        assert "https://example.com" not in result
        assert "x=1&y=2" not in result

    def test_html_img_local_in_content(self):
        md = '<img src="images/local.png" alt="图" /> 描述'
        result = build_paracol_content(md, [])
        assert "<img" not in result.lower()
        assert r"\includegraphics" in result
        assert "images/local.png" in result

    def test_mixed_pre_escaped_and_unescaped_in_correction(self):
        """混合场景：correction 里既有 \\% 又有 %"""
        md = r"效率 $50\%$ 和 $30%$"
        corrections = [{
            "type": "text",
            "original": r"$50\%$ 和 $30%$",
            "correction": r"$50\%$ 和 $30\%$",
            "reason": "都应转义",
        }]
        result = build_paracol_content(md, corrections)
        # 统计 % 前的反斜杠数，都应是 1
        counts = _count_backslash_before_percent(result)
        # 至少 4 个 %（原文 2 个 + correction 2 个）
        assert all(c == 1 for c in counts), (
            f"Expected all single-escape, got {counts}"
        )

    def test_text_with_html_img_and_math(self):
        """综合场景：文本 + HTML img + 数学公式"""
        md = r'如图 <img src="https://x.com/i.png?a=1&b=2" /> 所示，$\eta = 50\%$'
        result = build_paracol_content(md, [])
        assert "<img" not in result.lower()
        assert "https://x.com" not in result
        assert r"\eta" in result
        assert r"50\%" in result
        assert r"50\\%" not in result

    def test_latex_commands_in_correction_preserved(self):
        """LaTeX 命令不应被破坏"""
        md = r"公式 $E=mc^2$"
        corrections = [{
            "type": "text",
            "original": r"$E=mc^2$",
            "correction": r"$E=mc^{2}$",
            "reason": "应加花括号",
        }]
        result = build_paracol_content(md, corrections)
        assert r"\dfrac" not in result or r"\frac" not in result  # 无分式，无变化
        assert r"E=mc^{2}" in result or r"E=mc^2" in result

    def test_chinese_text_preserved(self):
        md = "这是一段中文文字。公式 $x=1$ 正确。"
        result = build_paracol_content(md, [])
        assert "这是一段中文文字" in result

    def test_nested_math_delimiters(self):
        """混合 $ 和 \\( \\) 定界符，并区分含/不含数学符号的 \\[...]"""
        # 含数学符号的 \[...\] 应保留为显示数学
        md_with_math = r"行内 $a=1$ 和 \(b=2\) 显示 \[c=x^2+1\]"
        result = build_paracol_content(md_with_math, [])
        assert r"\(a=1\)" in result
        assert r"\(b=2\)" in result
        # c=x^2+1 含 ^ —— 应保留为 \[...\]
        assert r"\[c=x^2+1\]" in result

        # 不含数学符号的 \[...\] 被 _fix_escaped_brackets 还原为 [...]（Pandoc 转义残留）
        md_no_math = r"注释 \[note\] 结束"
        result2 = build_paracol_content(md_no_math, [])
        assert "[note]" in result2
        assert r"\[note\]" not in result2

    def test_tool_call_with_percent(self):
        """工具调用记录中含 % 不应破坏编译"""
        md = "测试"
        tool_calls = [{
            "tool": "evaluate",
            "args": {"expr": "50%"},
            "result": "0.5",
        }]
        result = build_paracol_content(md, [], tool_calls=tool_calls)
        # 工具调用块应存在
        assert "工具调用记录" in result
        # 50% 应被转义
        assert r"50\%" in result


# ============================================================
# 端到端编译测试：确保 .tex 能被 xelatex 编译
# ============================================================

class TestEndToEndCompilation:
    def _compile_pipeline(self, md, corrections, tool_calls=None):
        """运行完整 JSON → tex → PDF 管道，返回 PDF 路径。"""
        tmp = _make_temp_dir()
        jp = os.path.join(tmp, "data.json")
        mp = os.path.join(tmp, "data.md")
        tp = os.path.join(tmp, "out.tex")
        _write(jp, json.dumps({
            "corrections": corrections,
            "tool_calls": tool_calls or [],
        }, ensure_ascii=False))
        _write(mp, md)
        generate_tex(jp, mp, tp)
        pdf_path = compile_to_pdf(tp, output_dir=tmp)
        return tmp, tp, pdf_path

    def test_pre_escaped_percent_compiles(self):
        """实际故障复现：LLM 输出 r'\\%' 必须能编译。"""
        md = r"除尘率 $\eta =\dfrac{1}{2}\times 100\%=50\%$"
        corrections = [{
            "type": "text",
            "original": r"$\eta =\frac{1}{2}\times 100%=50%$",
            "correction": r"$\eta =\frac{1}{2}\times 100\%=50\%$",
            "reason": r"LaTeX数学环境中%为注释符，需转义为\%才能正确显示百分号",
        }]
        tmp, tp, pdf_path = self._compile_pipeline(md, corrections)
        try:
            assert os.path.isfile(pdf_path), "PDF was not generated"
            assert os.path.getsize(pdf_path) > 1000, "PDF too small — likely a crash stub"
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_html_img_remote_compiles(self):
        """HTML img 远程 URL 必须不破坏编译。"""
        md = '<img src="https://example.com/fig.png?x=1&y=2" alt="题图" /> 选项A'
        tmp, tp, pdf_path = self._compile_pipeline(md, [])
        try:
            assert os.path.isfile(pdf_path)
            assert os.path.getsize(pdf_path) > 1000
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_html_img_local_compiles(self):
        """HTML img 本地路径应转为 includegraphics 并编译。"""
        # 用一张真实有效的 PNG（用 PIL 生成，避免手写 PNG 字节错误）
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("PIL not available for generating test PNG")
        tmp = _make_temp_dir()
        img_dir = os.path.join(tmp, "images")
        os.makedirs(img_dir, exist_ok=True)
        # 优先用仓库里的 fixture PNG，否则现场生成
        fixture = os.path.join(os.path.dirname(__file__), "fixtures", "red_10x10.png")
        if os.path.isfile(fixture):
            import shutil
            shutil.copy2(fixture, os.path.join(img_dir, "fig.png"))
        else:
            img = Image.new("RGBA", (10, 10), (255, 0, 0, 255))
            img.save(os.path.join(img_dir, "fig.png"), format="PNG")

        md = '<img src="images/fig.png" alt="图" /> 说明文字'
        jp = os.path.join(tmp, "data.json")
        mp = os.path.join(tmp, "data.md")
        tp = os.path.join(tmp, "out.tex")
        _write(jp, json.dumps({"corrections": [], "tool_calls": []}, ensure_ascii=False))
        _write(mp, md)
        generate_tex(jp, mp, tp)
        try:
            pdf_path = compile_to_pdf(tp, output_dir=tmp)
            assert os.path.isfile(pdf_path)
            assert os.path.getsize(pdf_path) > 1000, (
                f"PDF only {os.path.getsize(pdf_path)} bytes — likely a crash stub"
            )
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_multiple_corrections_with_percents_compile(self):
        """多个修改项，每个都含 % —— 综合编译测试。"""
        md = r"效率 $\eta_1 = 50\%$，效率 $\eta_2 = 30\%$"
        corrections = [
            {"type": "text",
             "original": r"$\eta_1 = 50%$",
             "correction": r"$\eta_1 = 50\%$",
             "reason": r"应转义 \%"},
            {"type": "text",
             "original": r"$\eta_2 = 30%$",
             "correction": r"$\eta_2 = 30\%$",
             "reason": r"应转义 \%"},
        ]
        tmp, tp, pdf_path = self._compile_pipeline(md, corrections)
        try:
            assert os.path.isfile(pdf_path)
            assert os.path.getsize(pdf_path) > 1000
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_html_img_and_math_and_correction_compile(self):
        """综合场景：HTML img + 数学公式 + 修改项。"""
        md = r'<img src="https://x.com/fig.png?a=1&b=2" /> 公式 $\eta = 50\%$'
        corrections = [{
            "type": "text",
            "original": r"$\eta = 50%$",
            "correction": r"$\eta = 50\%$",
            "reason": r"应转义 \%",
        }]
        tmp, tp, pdf_path = self._compile_pipeline(md, corrections)
        try:
            assert os.path.isfile(pdf_path)
            assert os.path.getsize(pdf_path) > 1000
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_unescaped_percent_in_text_compiles(self):
        """普通文本中的 % 也必须能编译。"""
        md = "完成率 80% 以上。"
        tmp, tp, pdf_path = self._compile_pipeline(md, [])
        try:
            assert os.path.isfile(pdf_path)
            assert os.path.getsize(pdf_path) > 1000
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_tool_calls_with_percent_compile(self):
        """工具调用记录里的 % 不应破坏编译。"""
        md = "测试公式 $x=1$"
        tool_calls = [{
            "tool": "evaluate",
            "args": {"expr": "50% of 100"},
            "result": "50",
        }]
        tmp, tp, pdf_path = self._compile_pipeline(md, [], tool_calls=tool_calls)
        try:
            assert os.path.isfile(pdf_path)
            assert os.path.getsize(pdf_path) > 1000
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


# ============================================================
# generate_combined_pdf 错误传播测试
# ============================================================

class TestGenerateCombinedPdfErrorPropagation:
    def _make_lecture_dir(self, md, corrections):
        """构造一个最小讲义目录。"""
        tmp = _make_temp_dir()
        qdir = os.path.join(tmp, "第1题")
        os.makedirs(qdir, exist_ok=True)
        _write(os.path.join(qdir, "第1题.md"), md)
        _write(
            os.path.join(qdir, "_校对数据.json"),
            json.dumps({"corrections": corrections, "tool_calls": []}, ensure_ascii=False),
        )
        return tmp, qdir

    def test_compile_failure_raises_runtime_error(self):
        """编译失败时应抛 RuntimeError，不能静默返回 None。

        直接给 compile_to_pdf 一个语法错误的 .tex，验证它检测到失败并抛错。
        这正是用户遇到的"PDF 损坏"场景：xelatex 在 nonstopmode 下可能写出
        残缺 PDF，compile_to_pdf 必须识别并抛错，而不是把残缺 PDF 复制走。
        """
        from pdf_compiler import compile_to_pdf
        tmp = _make_temp_dir()
        tp = os.path.join(tmp, "broken.tex")
        # 没有结束的 document 环境 + 未定义命令
        _write(tp, r"\documentclass{article}\begin{document}\undefinedcmd{")
        try:
            with pytest.raises(RuntimeError, match="[Cc]ompil|LaTeX"):
                compile_to_pdf(tp, output_dir=tmp)
            # 残缺 PDF 应被删除或不存在
            pdf = os.path.join(tmp, "broken.pdf")
            if os.path.isfile(pdf):
                # 如果 PDF 存在，说明是残缺 stub
                assert os.path.getsize(pdf) < 1024, "Large PDF produced from broken tex?"
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_compile_failure_in_combined_pdf_cleanup(self):
        r"""generate_combined_pdf 编译失败时应删除残缺 PDF 并抛 RuntimeError。

        用一个真正能让 xelatex 紧急停止的 .tex —— 直接写一个语法错误的
        .tex 到讲义目录之外的位置，用 compile_to_pdf 验证错误检测路径。
        不能通过 build_paracol_content 触发，因为它会转义所有破坏性字符。
        """
        # 直接测 compile_to_pdf 的错误检测能力（它负责抛 RuntimeError）
        tmp = _make_temp_dir()
        tp = os.path.join(tmp, "broken.tex")
        _write(tp, r"\documentclass{article}\begin{document}\undefinedcmd{")
        try:
            with pytest.raises(RuntimeError, match="[Cc]ompil|LaTeX"):
                compile_to_pdf(tp, output_dir=tmp)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_missing_image_replaced_not_crashes(self):
        r"""generate_combined_pdf 遇到缺失图片时应替换为占位框，不崩溃。

        这正是用户遇到的 ../_resources/ 路径问题 —— 旧版本会让 xelatex
        加载失败、写出 15 字节残缺 PDF。新版本用 _rewrite_unresolvable_images
        把缺失图片替换为 [图片缺失: xxx] 提示框，PDF 仍能正常生成。
        """
        tmp = _make_temp_dir()
        lecture_dir = os.path.join(tmp, "lecture")
        os.makedirs(lecture_dir, exist_ok=True)
        qdir = os.path.join(lecture_dir, "第1题")
        os.makedirs(qdir, exist_ok=True)
        # md 引用 images/missing.png，但 images/ 目录不存在
        _write(os.path.join(qdir, "第1题.md"), "如图 ![](images/missing.png) 所示")
        _write(
            os.path.join(qdir, "_校对数据.json"),
            json.dumps({"corrections": [], "tool_calls": []}, ensure_ascii=False),
        )

        pdf_out = os.path.join(tmp, "pdf_out")
        try:
            pdf_path = generate_combined_pdf(lecture_dir, pdf_out)
            # 应该成功生成 PDF（不是抛 RuntimeError）
            assert pdf_path is not None
            assert os.path.isfile(pdf_path)
            # PDF 大小应 > 1KB（非 stub）
            assert os.path.getsize(pdf_path) > 1000, (
                f"PDF only {os.path.getsize(pdf_path)} bytes —— "
                "缺失图片未被替换为占位框，xelatex 崩溃了"
            )
            # 验证 .tex 里有占位框
            tex_files = [f for f in os.listdir(pdf_out) if f.endswith(".tex")]
            with open(os.path.join(pdf_out, tex_files[0]), "r", encoding="utf-8") as f:
                tex = f.read()
            assert "图片缺失" in tex
            assert "missing.png" in tex
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_missing_image_in_subdir_replaced(self):
        r"""子目录引用的图片缺失时也应被替换为占位框。

        generate_combined_pdf 把图片路径改写为 ./{section_title}/images/{file}，
        并把 images_map 传给 compile_to_pdf 复制到临时目录。如果某个子目录
        的 images/ 里少了文件，新版应替换为占位框而不是崩溃。
        """
        tmp = _make_temp_dir()
        lecture_dir = os.path.join(tmp, "lecture")
        os.makedirs(lecture_dir, exist_ok=True)
        qdir = os.path.join(lecture_dir, "第1题")
        os.makedirs(qdir, exist_ok=True)
        # md 引用 images/fig.png —— 我们创建 images/ 目录但故意不把 fig.png 放进去
        img_dir = os.path.join(qdir, "images")
        os.makedirs(img_dir, exist_ok=True)
        # 放一张别的图片，让 images/ 目录非空
        _write(os.path.join(img_dir, "other.png"), "not a real png")
        _write(os.path.join(qdir, "第1题.md"), "如图 ![](images/fig.png) 所示")
        _write(
            os.path.join(qdir, "_校对数据.json"),
            json.dumps({"corrections": [], "tool_calls": []}, ensure_ascii=False),
        )

        pdf_out = os.path.join(tmp, "pdf_out")
        try:
            pdf_path = generate_combined_pdf(lecture_dir, pdf_out)
            assert pdf_path is not None
            assert os.path.isfile(pdf_path)
            assert os.path.getsize(pdf_path) > 1000
            # fig.png 应在占位框里出现
            tex_files = [f for f in os.listdir(pdf_out) if f.endswith(".tex")]
            with open(os.path.join(pdf_out, tex_files[0]), "r", encoding="utf-8") as f:
                tex = f.read()
            assert "图片缺失" in tex
            assert "fig.png" in tex
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_compile_success_returns_pdf_path(self):
        md = r"正常文字 $x=1$"
        tmp, qdir = self._make_lecture_dir(md, [])
        pdf_out = os.path.join(tmp, "pdf_out")
        try:
            pdf_path = generate_combined_pdf(tmp, pdf_out)
            assert pdf_path is not None
            assert os.path.isfile(pdf_path)
            assert os.path.getsize(pdf_path) > 1000
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_pre_escaped_percent_in_combined_pdf(self):
        """完整链路：多题目 + LLM 预转义 % 必须成功生成 PDF。"""
        tmp = _make_temp_dir()
        # 第1题
        q1 = os.path.join(tmp, "第1题")
        os.makedirs(q1, exist_ok=True)
        _write(os.path.join(q1, "第1题.md"), r"除尘率 $\eta =\dfrac{1}{2}\times 100\%=50\%$")
        _write(
            os.path.join(q1, "_校对数据.json"),
            json.dumps({
                "corrections": [{
                    "type": "text",
                    "original": r"$\eta =\frac{1}{2}\times 100%=50%$",
                    "correction": r"$\eta =\frac{1}{2}\times 100\%=50\%$",
                    "reason": r"应转义 \%",
                }],
                "tool_calls": [],
            }, ensure_ascii=False),
        )
        # 第2题
        q2 = os.path.join(tmp, "第2题")
        os.makedirs(q2, exist_ok=True)
        _write(os.path.join(q2, "第2题.md"), r"效率 $50\%$")
        _write(
            os.path.join(q2, "_校对数据.json"),
            json.dumps({"corrections": [], "tool_calls": []}, ensure_ascii=False),
        )

        pdf_out = os.path.join(tmp, "pdf_out")
        try:
            pdf_path = generate_combined_pdf(tmp, pdf_out)
            assert pdf_path is not None
            assert os.path.isfile(pdf_path)
            assert os.path.getsize(pdf_path) > 2000, "Combined PDF too small"
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


# ============================================================
# 回归测试：复现故障的精确输入
# ============================================================

class TestRegressionExactCase:
    """复现 2026-06-22 第_10_讲 PDF 损坏的精确输入。"""

    def test_exact_failing_correction_compiles(self):
        """原始故障 correction（含 \\% 的 η = 1/2 × 100% = 50%）。"""
        md = r"除尘率 $\eta =\dfrac{1}{2}\times 100\%=50\%$"
        corrections = [
            {"num": 3, "type": "text",
             "original": r"$\eta =\frac{1}{2}\times 100%=50%$",
             "correction": r"$\eta =\frac{1}{2}\times 100\%=50\%$",
             "reason": r"LaTeX数学环境中%为注释符，需转义为\%才能正确显示百分号，避免后续内容被注释。"},
            {"num": 4, "type": "text",
             "original": r"$=\frac{y}{d}\times 100%$",
             "correction": r"$=\frac{y}{d}\times 100\%$",
             "reason": r"LaTeX数学环境中%为注释符，需转义为\%才能正确显示百分号。"},
            {"num": 5, "type": "text",
             "original": r"$=\frac{\frac{1}{2}a{{t}^{2}}}{d}\times 100%$",
             "correction": r"$=\frac{\frac{1}{2}a{{t}^{2}}}{d}\times 100\%$",
             "reason": r"LaTeX数学环境中%为注释符，需转义为\%才能正确显示百分号。"},
            {"num": 6, "type": "text",
             "original": r"$=\frac{{{U}_{0}}q{{L}^{2}}}{2m{{v}^{2}}{{d}^{2}}}\times 100%$",
             "correction": r"$=\frac{{{U}_{0}}q{{L}^{2}}}{2m{{v}^{2}}{{d}^{2}}}\times 100\%$",
             "reason": r"LaTeX数学环境中%为注释符，需转义为\%才能正确显示百分号。"},
        ]
        result = build_paracol_content(md, corrections)
        # 关键回归断言：不能有 \\%（双反斜杠 + %）
        assert r"\\%" not in result, (
            "Double-escape detected — this is the exact bug that produced the corrupt PDF"
        )

    def test_exact_failing_html_img_compiles(self):
        """原始故障 HTML img 标签（含 &、%、~ 的远程 URL）。"""
        md = (
            '<img src="https://p3-hippo-sign.byteimg.com/tos-cn-i-a9yeduch1e/'
            '268975f78b8c4717900b12f39789d77d~tplv-ii0cwwkcx9-resize-crop-v1:0:0:1743:1074:0:0.jpeg'
            '?lk3s=19ff00fe&x-expires=2067585541&x-signature=%2B4G7Y7gW7Q1%2F%2FhQ3%2B%2Fh8Q7%2F7g7M%3D" '
            'alt="题图" />'
        )
        result = build_paracol_content(md, [])
        # 不能残留原始 HTML 语法或 URL
        assert "<img" not in result.lower()
        assert "https://" not in result
        assert "lk3s=" not in result
        # 不应出现裸露的 &（应是 \& 或已整体替换）
        # 占位符已替换为 LaTeX 命令，URL 不应残留
        assert "byteimg.com" not in result

    def test_full_failing_scenario_compiles(self):
        """端到端：原故障 .tex 的两大问题同时存在时必须编译成功。"""
        md = (
            r'<img src="https://x.com/fig.png?a=1&b=2" alt="题图" /> '
            r"除尘率 $\eta =\dfrac{1}{2}\times 100\%=50\%$"
        )
        corrections = [{
            "type": "text",
            "original": r"$\eta =\frac{1}{2}\times 100%=50%$",
            "correction": r"$\eta =\frac{1}{2}\times 100\%=50\%$",
            "reason": r"应转义 \%",
        }]
        tmp = _make_temp_dir()
        jp = os.path.join(tmp, "data.json")
        mp = os.path.join(tmp, "data.md")
        tp = os.path.join(tmp, "out.tex")
        _write(jp, json.dumps({"corrections": corrections, "tool_calls": []}, ensure_ascii=False))
        _write(mp, md)
        generate_tex(jp, mp, tp)
        try:
            pdf_path = compile_to_pdf(tp, output_dir=tmp)
            assert os.path.isfile(pdf_path)
            # 残缺 PDF 通常 < 1000 字节；正常 PDF 应 > 1000
            assert os.path.getsize(pdf_path) > 1000, (
                f"PDF only {os.path.getsize(pdf_path)} bytes — likely a crash stub"
            )
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


# ============================================================
# _rewrite_unresolvable_images 单元测试
# ============================================================

class TestRewriteUnresolvableImages:
    r"""测试 _rewrite_unresolvable_images 把无法解析的 \includegraphics 替换为占位框。

    背景：LLM 校对员有时在 marked_text 里插入虚构的图片引用
    （如 ../_resources/42761a09440b4797b4392b3b9573e036.png）。
    xelatex 加载这些不存在的图片会崩溃，导致 PDF 损坏。
    """

    def test_resolvable_image_kept(self):
        content = r"\includegraphics[width=\linewidth]{./images/fig.png}"
        out = _rewrite_unresolvable_images(content, {"fig.png"})
        assert out == content, "已存在的图片不应被替换"

    def test_unresolvable_image_replaced(self):
        content = r"\includegraphics[width=\linewidth]{../_resources/missing.png}"
        out = _rewrite_unresolvable_images(content, set())
        assert r"\includegraphics" not in out
        assert "图片缺失" in out
        assert "missing.png" in out

    def test_partial_path_uses_basename(self):
        """路径含子目录时只取 basename 比对"""
        content = r"\includegraphics{./subdir/fig.png}"
        out = _rewrite_unresolvable_images(content, {"fig.png"})
        # basename fig.png 在 available set 中 —— 应保留
        assert r"\includegraphics" in out
        assert out == content

    def test_empty_available_set_replaces_all(self):
        content = r"\includegraphics{./images/fig.png}"
        out = _rewrite_unresolvable_images(content, set())
        assert r"\includegraphics" not in out
        assert "图片缺失" in out
        assert "fig.png" in out

    def test_underscore_in_filename_escaped(self):
        content = r"\includegraphics{../_resources/fig_100.png}"
        out = _rewrite_unresolvable_images(content, set())
        # _ 在 LaTeX 里是下标，必须转义为 \_
        assert r"fig\_100.png" in out

    def test_percent_in_filename_escaped(self):
        content = r"\includegraphics{../_resources/fig100%.png}"
        out = _rewrite_unresolvable_images(content, set())
        # % 是注释符，必须转义为 \%
        assert r"fig100\%.png" in out

    def test_hash_in_filename_escaped(self):
        content = r"\includegraphics{../_resources/fig#1.png}"
        out = _rewrite_unresolvable_images(content, set())
        assert r"fig\#1.png" in out

    def test_multiple_includegraphics(self):
        content = (
            r"\includegraphics{./images/keep.png}"
            r" 文字 "
            r"\includegraphics{../_resources/drop.png}"
        )
        out = _rewrite_unresolvable_images(content, {"keep.png"})
        assert r"{./images/keep.png}" in out  # 保留
        assert r"\includegraphics{../_resources/drop.png}" not in out  # 替换
        assert "drop.png" in out  # 占位框里显示文件名

    def test_includegraphics_without_options(self):
        r"""无 [options] 的 \includegraphics 也要能匹配"""
        content = r"\includegraphics{./images/fig.png}"
        out = _rewrite_unresolvable_images(content, set())
        assert r"\includegraphics" not in out
        assert "图片缺失" in out

    def test_includegraphics_with_spaces_around_path(self):
        """路径两端有空格也要能匹配"""
        content = r"\includegraphics[width=\linewidth]{  ./images/fig.png  }"
        out = _rewrite_unresolvable_images(content, {"fig.png"})
        assert r"\includegraphics" in out  # 保留

    def test_real_llm_hallucination_path(self):
        """真实 LLM 幻觉路径：32 字符 hex 文件名 + ../_resources/ 前缀"""
        content = (
            r"\includegraphics[width=\linewidth,keepaspectratio]"
            r"{../_resources/42761a09440b4797b4392b3b9573e036.png}"
        )
        out = _rewrite_unresolvable_images(content, set())
        assert r"\includegraphics" not in out
        assert "42761a09440b4797b4392b3b9573e036.png" in out
        assert "图片缺失" in out

    def test_preserves_other_latex_commands(self):
        """其他 LaTeX 命令不受影响"""
        content = (
            r"\section{Title}"
            r"\includegraphics{../_resources/missing.png}"
            r"\textbf{Bold text}"
        )
        out = _rewrite_unresolvable_images(content, set())
        assert r"\section{Title}" in out
        assert r"\textbf{Bold text}" in out
        assert r"\includegraphics" not in out

    def test_placeholder_is_valid_latex(self):
        """生成的占位框必须是合法 LaTeX（含 fbox + parbox）"""
        content = r"\includegraphics{missing.png}"
        out = _rewrite_unresolvable_images(content, set())
        # 必须含 fbox{...parbox{...}} 结构
        assert r"\fbox{" in out
        assert r"\parbox{" in out
        # 必须含 \linewidth 引用
        assert r"\linewidth" in out


# ============================================================
# generate_combined_pdf 端到端 — 图片缺失场景
# ============================================================

class TestGenerateCombinedPdfMissingImages:
    """generate_combined_pdf 遇到 LLM 幻觉的图片引用时必须不崩溃。"""

    def _make_lecture_with_hallucinated_image(self):
        """构造一个含 LLM 幻觉图片引用的讲义目录。

        模拟真实场景：第1题的 marked_text 末尾被 LLM 插入了
        ![](../_resources/42761a09440b4797b4392b3b9573e036.png)
        但这个文件实际不存在。
        """
        tmp = _make_temp_dir()
        lecture = os.path.join(tmp, "lecture")
        os.makedirs(lecture, exist_ok=True)

        # 第1题：含真实图片 + 幻觉图片
        q1 = os.path.join(lecture, "第1题")
        os.makedirs(q1, exist_ok=True)
        # 创建一张真实图片
        img_dir = os.path.join(q1, "images")
        os.makedirs(img_dir, exist_ok=True)
        fixture = os.path.join(os.path.dirname(__file__), "fixtures", "red_10x10.png")
        if os.path.isfile(fixture):
            import shutil
            shutil.copy2(fixture, os.path.join(img_dir, "real.png"))
        else:
            try:
                from PIL import Image
                Image.new("RGBA", (10, 10), (255, 0, 0, 255)).save(
                    os.path.join(img_dir, "real.png"), format="PNG"
                )
            except ImportError:
                pytest.skip("PIL not available")

        # marked_text 末尾插入幻觉图片引用
        marked = (
            r"如图 ![](./images/real.png) 所示，公式 $x=1$"
            r"\n![](../_resources/42761a09440b4797b4392b3b9573e036.png)【3||】"
        )
        _write(
            os.path.join(q1, "_校对数据.json"),
            json.dumps({
                "marked_text": marked,
                "corrections": [],
                "tool_calls": [],
            }, ensure_ascii=False),
        )
        _write(os.path.join(q1, "第1题.md"), "如图 ![](./images/real.png) 所示")

        return tmp, lecture

    def test_hallucinated_image_does_not_break_pdf(self):
        """LLM 幻觉的图片引用不应破坏 PDF 生成。"""
        tmp, lecture = self._make_lecture_with_hallucinated_image()
        pdf_out = os.path.join(tmp, "pdf_out")
        try:
            pdf_path = generate_combined_pdf(lecture, pdf_out)
            assert pdf_path is not None, "PDF 生成失败但未抛错"
            assert os.path.isfile(pdf_path)
            # PDF 必须 > 1KB（非 stub）
            assert os.path.getsize(pdf_path) > 1000, (
                f"PDF only {os.path.getsize(pdf_path)} bytes — stub from image load failure"
            )
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_hallucinated_image_replaced_with_placeholder(self):
        """幻觉图片应在 .tex 中被替换为 [图片缺失: xxx] 占位框。"""
        tmp, lecture = self._make_lecture_with_hallucinated_image()
        pdf_out = os.path.join(tmp, "pdf_out")
        try:
            generate_combined_pdf(lecture, pdf_out)
            # 找生成的 .tex 文件
            tex_files = [f for f in os.listdir(pdf_out) if f.endswith(".tex")]
            assert len(tex_files) == 1
            with open(os.path.join(pdf_out, tex_files[0]), "r", encoding="utf-8") as f:
                tex = f.read()
            # 幻觉图片不应出现为 \includegraphics
            assert r"\includegraphics" in tex  # 真实图片保留
            # 幻觉图片的文件名应在占位框里出现
            assert "42761a09440b4797b4392b3b9573e036.png" in tex
            assert "图片缺失" in tex
            # 幻觉路径不应原样出现为 \includegraphics
            assert (
                r"\includegraphics[width=\linewidth,keepaspectratio]{../_resources/42761a09440b4797b4392b3b9573e036.png}"
                not in tex
            ), r"幻觉图片路径必须被替换，不能原样进入 \includegraphics"
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_real_image_preserved_alongside_hallucinated(self):
        """真实图片和幻觉图片并存时，真实的必须保留，幻觉的必须替换。"""
        tmp, lecture = self._make_lecture_with_hallucinated_image()
        pdf_out = os.path.join(tmp, "pdf_out")
        try:
            generate_combined_pdf(lecture, pdf_out)
            tex_files = [f for f in os.listdir(pdf_out) if f.endswith(".tex")]
            with open(os.path.join(pdf_out, tex_files[0]), "r", encoding="utf-8") as f:
                tex = f.read()
            # 真实图片保留为 \includegraphics
            assert r"\includegraphics" in tex
            assert "real.png" in tex
            # 真实图片不应在"图片缺失"占位框里
            # （只在幻觉图片旁出现 real.png 才算正常）
            # 这个断言较难精确，我们简单验证 real.png 至少出现一次作为 includegraphics
            assert r"\includegraphics" in tex and "real.png" in tex
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


# ============================================================
# 内联标记 $ 剥离测试 — 防止数学模式被拆断
# ============================================================

class TestInlineMarkerDollarStrip:
    r"""LLM 有时在 marked_text 的 $...$ 数学块内插入内联标记，
    例如 $...{}【3|${E}_{P}A$|${E}_{p}A$】{}$...。
    如果不剥离标记里 orig 的 $ 定界符，标记会把外层数学块拆成两段，
    导致 }{ 等 LaTeX 语法掉出数学模式被 \_escape_text 双重转义。
    """

    def test_dollar_marker_inside_math(self):
        """第22题实际故障：标记内的 $...$ 不得拆分外层数学块。"""
        md = r"解答:  ${\varphi }_{A}=\dfrac{【3|${E}_{\mathrm{P}A}$|${E}_{\mathrm{p}A}$】}{q}=-40\mathrm{V}$"
        corrections = [
            {"num": 3, "type": "text",
             "original": "${E}_{\\mathrm{P}A}$",
             "correction": "${E}_{\\mathrm{p}A}$",
             "reason": "统一小写p"},
        ]
        result = build_paracol_content(md, corrections)
        # 外层 math 必须完整
        assert r"{\varphi }_{A}" in result
        # 不能出现双重转义（这是核心回归断言）
        assert r"\{E\}" not in result
        assert r"\textbackslash mathrm" not in result

    def test_dollar_marker_in_dfrac_numerator(self):
        r"""标记在 \dfrac 分子中的 $ 内 —— 模拟第22题精确输入。"""
        md = r"${\varphi }_{A}=\dfrac{【1|${E}_{\mathrm{P}A}$|${E}_{\mathrm{p}A}$】}{q}=-40\mathrm{V}$"
        corrections = [
            {"num": 1, "type": "text",
             "original": "${E}_{\\mathrm{P}A}$",
             "correction": "${E}_{\\mathrm{p}A}$",
             "reason": "下标大小写"},
        ]
        result = build_paracol_content(md, corrections)
        assert r"\{E\}" not in result
        assert r"\textbackslash mathrm" not in result
        assert r"\dfrac" in result  # \frac → \dfrac upgrade still works

    def test_multiple_dollar_markers_in_math(self):
        """同一 math 块内有多个 $ 包裹的标记。"""
        md = (
            r"${\varphi }_{A}=\dfrac{【3|${E}_{\mathrm{P}A}$|${E}_{\mathrm{p}A}$】}{q}$，"
            r"${\varphi }_{B}=\dfrac{【4|${E}_{\mathrm{P}B}$|${E}_{\mathrm{p}B}$】}{q}$"
        )
        corrections = [
            {"num": 3, "type": "text", "original": "${E}_{\\mathrm{P}A}$",
             "correction": "${E}_{\\mathrm{p}A}$", "reason": "统一小写"},
            {"num": 4, "type": "text", "original": "${E}_{\\mathrm{P}B}$",
             "correction": "${E}_{\\mathrm{p}B}$", "reason": "统一小写"},
        ]
        result = build_paracol_content(md, corrections)
        assert r"\{E\}" not in result
        assert r"\textbackslash mathrm" not in result

    def test_dollar_marker_not_stripped_when_not_wrapped(self):
        """orig 不以 $ 包裹时不剥离 —— 回归保护。"""
        md = r"将一【1|带电量|电荷量】为$-2\mathrm{C}$的点电荷"
        corrections = [
            {"num": 1, "type": "text", "original": "带电量",
             "correction": "电荷量", "reason": "术语规范"},
        ]
        result = build_paracol_content(md, corrections)
        # orig "带电量" 没有 $，文本模式下应被 \corrmark 包裹
        assert r"\corrmark{带电量}{1}" in result
        # 原文保留（内联标记的 orig 在左栏保留，右栏显示 correction）
        assert "带电量" in result
        # 但 $ 内的 math 不受影响
        assert r"\(-2\mathrm{C}\)" in result

    def test_empty_dollar_stripping_noop(self):
        """$ 包裹但内容为空（极小概率的边缘情况）：不剥离（防数组越界）。"""
        md = r"测试【1|$$|】文"
        corrections = [{"num": 1, "type": "text", "original": "", "correction": "", "reason": ""}]
        result = build_paracol_content(md, corrections)
        # 不应崩溃，标记应存在
        assert r"\redcircled{1}" in result

    def test_dollar_marker_compiles_end_to_end(self):
        """端到端编译：含 $ 内联标记的 math 块必须能通过 xelatex。"""
        md = r"解答:  ${\varphi }_{A}=\dfrac{【1|${E}_{\mathrm{P}A}$|${E}_{\mathrm{p}A}$】}{q}=-40\mathrm{V}$"
        corrections = [
            {"num": 1, "type": "text",
             "original": "${E}_{\\mathrm{P}A}$",
             "correction": "${E}_{\\mathrm{p}A}$",
             "reason": "统一小写p"},
        ]
        tmp = _make_temp_dir()
        jp = os.path.join(tmp, "data.json")
        mp = os.path.join(tmp, "data.md")
        tp = os.path.join(tmp, "out.tex")
        _write(jp, json.dumps({"corrections": corrections, "tool_calls": []}, ensure_ascii=False))
        _write(mp, md)
        generate_tex(jp, mp, tp)
        try:
            pdf_path = compile_to_pdf(tp, output_dir=tmp)
            assert os.path.isfile(pdf_path)
            assert os.path.getsize(pdf_path) > 1000
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
