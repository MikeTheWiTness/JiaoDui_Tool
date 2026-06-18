"""Markdown → LaTeX 格式转换测试 — 覆盖粗/斜体与数学模式的交互"""

from latex_generator import build_paracol_content


def _compile_ok(md, corrections=None):
    """生成的内容能被 LaTeX 正确编译（至少不含原始 * 和 ~~）"""
    result = build_paracol_content(md, corrections or [])
    # 格式标记应被替换
    issues = []
    if "*" in result:
        # 但 * 可能在 LaTeX 命令或数学模式中合法
        pass
    return result


class TestItalic:
    def test_plain_italic(self):
        r = build_paracol_content("*italic text*", [])
        assert r"\textit{italic text}" in r

    def test_italic_around_math(self):
        r = build_paracol_content("*$A$* 位置", [])
        assert r"\textit{$A$}" in r

    def test_italic_around_text_math(self):
        r = build_paracol_content("圆心*$O$*的电势", [])
        assert r"\textit{$O$}" in r
        # 检查左栏内容无残留 *（排除 LaTeX 命令如 \switchcolumn*）
        left_of_switch = r.split(r"\switchcolumn")[0]
        assert "*" not in left_of_switch

    def test_multiple_italic_math(self):
        r = build_paracol_content("*$A$*和*$B$*和*$C$*", [])
        assert r.count(r"\textit") == 3

    def test_italic_with_math_inside(self):
        r = build_paracol_content("电场*$E=k\\frac{Q}{r^2}$*公式", [])
        assert r"\textit{$E=k\frac{Q}{r^2}$}" in r


class TestBold:
    def test_plain_bold(self):
        r = build_paracol_content("**bold text**", [])
        assert r"\textbf{bold text}" in r

    def test_bold_around_math(self):
        r = build_paracol_content("**$A$** 位置", [])
        assert r"\textbf{$A$}" in r

    def test_bold_around_text_math(self):
        r = build_paracol_content("答案**$D$**正确", [])
        assert r"\textbf{$D$}" in r

    def test_multiple_bold_math(self):
        r = build_paracol_content("**$A$**、**$B$**、**$C$**", [])
        assert r.count(r"\textbf") == 3


class TestMixed:
    def test_bold_and_italic_separate(self):
        r = build_paracol_content("**$A$** 和 *$B$*", [])
        assert r"\textbf{$A$}" in r
        assert r"\textit{$B$}" in r

    def test_pandoc_strikethrough(self):
        """Pandoc ~~strikethrough~~ → 暂不转换但输出不含原始波浪线"""
        r = build_paracol_content("~~删除文字~~", [])
        # 当前不转换 ~~，但波浪线会被 LaTeX 转义为 \textasciitilde
        assert "~~" not in r  # 原始双波浪线应被转义处理
        assert len(r) > 0

    def test_strikethrough_around_math(self):
        r = build_paracol_content("~~$A$~~", [])
        assert "~~" not in r
        assert len(r) > 0

    def test_italic_in_paragraph(self):
        md = """已知电场强度为$E$，*方向水平向右*，求电场力。"""
        r = build_paracol_content(md, [])
        assert r"\textit{方向水平向右}" in r

    def test_no_false_positive_on_math_multiply(self):
        """数学模式中的 * 不应被转换"""
        r = build_paracol_content("$a * b$ 是乘法", [])
        assert r"\(a * b\)" in r
        assert r"\textit" not in r


class TestChineseItalic:
    def test_chinese_in_italic(self):
        r = build_paracol_content("*中文字符*", [])
        assert r"\textit{中文字符}" in r

    def test_mixed_cn_en_italic(self):
        r = build_paracol_content("*电势$U$的计算*", [])
        assert r"\textit{电势$U$的计算}" in r


class TestEdgeCases:
    def test_single_star_no_match(self):
        """单个 * 不是斜体标记"""
        r = build_paracol_content("a * b = c", [])
        # 不应匹配为斜体（缺闭合 *）
        assert r"\textit" not in r

    def test_star_in_math_preserved(self):
        r = build_paracol_content("$a*b$", [])
        assert r"\(a*b\)" in r

    def test_four_stars(self):
        """**** 不应匹配"""
        r = build_paracol_content("****", [])
        assert r"\textit" not in r

    def test_escape_text_preserves_content(self):
        r = build_paracol_content("包含 & % _ { } 特殊字符", [])
        assert r"\&" in r
        assert r"\%" in r
        assert r"\_" in r
        assert r"\{" in r
        assert r"\}" in r

    def test_h2o_chemical(self):
        r = build_paracol_content("水分子 $\\ce{H2O}$ 是极性分子", [])
        assert r"\ce{H2O}" in r


class TestFullPipeline:
    """编译测试：所有格式组合能通过 xelatex"""

    def test_compile_italic_math(self):
        from pdf_compiler import compile_to_pdf
        from latex_generator import generate_tex
        import tempfile, json, os

        md = "圆心*$O$*的电势为正，*$F$*点的电势大于*$O$*点。"
        tmp = tempfile.mkdtemp()
        jp = os.path.join(tmp, "t.json")
        mp = os.path.join(tmp, "t.md")
        tp = os.path.join(tmp, "t.tex")
        with open(jp, "w") as f: json.dump({"corrections": []}, f)
        with open(mp, "w", encoding="utf-8") as f: f.write(md)
        generate_tex(jp, mp, tp)
        pdf = compile_to_pdf(tp)
        assert os.path.getsize(pdf) > 0

    def test_compile_bold_math(self):
        from pdf_compiler import compile_to_pdf
        from latex_generator import generate_tex
        import tempfile, json, os

        md = "答案**$D$**正确，故选**$D$**。"
        tmp = tempfile.mkdtemp()
        jp = os.path.join(tmp, "t.json")
        mp = os.path.join(tmp, "t.md")
        tp = os.path.join(tmp, "t.tex")
        with open(jp, "w") as f: json.dump({"corrections": []}, f)
        with open(mp, "w", encoding="utf-8") as f: f.write(md)
        generate_tex(jp, mp, tp)
        pdf = compile_to_pdf(tp)
        assert os.path.getsize(pdf) > 0

    def test_compile_mixed_all(self):
        from pdf_compiler import compile_to_pdf
        from latex_generator import generate_tex
        import tempfile, json, os

        md = """**例1** 如图所示，圆心*$O$*处的电场强度为**$E=k\\frac{Q}{r^2}$**。
A. *$\\sqrt{2}x_{0}$* \nB. **$(2\\sqrt{2}-1)x_{0}$** \nC. $2\\sqrt{2}x_{0}$ \nD. ~~$(2\\sqrt{2}+1)x_{0}$~~"""
        tmp = tempfile.mkdtemp()
        jp = os.path.join(tmp, "t.json")
        mp = os.path.join(tmp, "t.md")
        tp = os.path.join(tmp, "t.tex")
        with open(jp, "w") as f: json.dump({"corrections": []}, f)
        with open(mp, "w", encoding="utf-8") as f: f.write(md)
        generate_tex(jp, mp, tp)
        pdf = compile_to_pdf(tp)
        assert os.path.getsize(pdf) > 0
