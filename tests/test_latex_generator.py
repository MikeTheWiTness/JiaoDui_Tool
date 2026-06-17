"""
latex_generator 测试套件
测试行为而非实现——验证 JSON + .md → .tex 生成的端到端行为。
"""
import json
import os
import tempfile
import pytest

from pdf_compiler import compile_to_pdf


def _write_temp_json(data: dict) -> str:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(data, tmp)
    tmp.close()
    return tmp.name


def _write_temp_md(content: str) -> str:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8")
    tmp.write(content)
    tmp.close()
    return tmp.name


class TestModuleExists:
    def test_module_imports(self):
        import latex_generator
        assert hasattr(latex_generator, "generate_tex")


class TestTextCorrection:
    def test_marker_in_content(self):
        from latex_generator import build_paracol_content

        md = "金刚石中C---C键键长更短。"
        corrections = [{"type": "text", "original": "C---C键", "correction": "C-C键", "reason": "符号错误"}]
        result = build_paracol_content(md, corrections)
        assert r"\textsuperscript{\textcolor{red}{\textcircled{1}}}" in result

    def test_reason_in_right_column(self):
        from latex_generator import build_paracol_content

        md = "测试文字C---C键在这里。"
        corrections = [{"type": "text", "original": "C---C键", "correction": "C-C键", "reason": "符号错误"}]
        result = build_paracol_content(md, corrections)
        assert "符号错误" in result
        assert r"\textcircled{1}" in result

    def test_multiple_markers(self):
        from latex_generator import build_paracol_content

        md = "甲说：E=mc2。乙说：F=ma。"
        corrections = [
            {"type": "text", "original": "mc2", "correction": "mc^2", "reason": "缺上标"},
            {"type": "text", "original": "ma", "correction": "m a", "reason": "缺空格"},
        ]
        result = build_paracol_content(md, corrections)
        assert r"\textcircled{1}" in result
        assert r"\textcircled{2}" in result


class TestRewriteCorrection:
    def test_rewrite_marker(self):
        from latex_generator import build_paracol_content

        md = "碘晶体层内和层间均为分子间作用力，是分子晶体。"
        corrections = [{"type": "rewrite", "original": "碘晶体层内和层间均为分子间作用力，是分子晶体。",
                        "correction": "碘晶体中分子间以范德华力结合。", "reason": "概念混淆"}]
        result = build_paracol_content(md, corrections)
        assert r"\textsuperscript{\textcolor{red}{\textcircled{1}}}" in result

    def test_reason_in_right(self):
        from latex_generator import build_paracol_content

        md = "这需要重写。"
        corrections = [{"type": "rewrite", "original": "这需要重写。",
                        "correction": "这是重写后的段落。", "reason": "表述不严谨"}]
        result = build_paracol_content(md, corrections)
        assert "表述不严谨" in result


class TestRegionCorrection:
    def test_region_in_right(self):
        from latex_generator import build_paracol_content

        md = "第（1）题配图如下所示。"
        corrections = [{"type": "region", "location": "第（1）题配图",
                        "correction": "配图B和C标注互换", "reason": "标注错误"}]
        result = build_paracol_content(md, corrections)
        assert "标注错误" in result


class TestFractionUpgrade:
    def test_frac_becomes_dfrac(self):
        from latex_generator import build_paracol_content
        md = "公式 $\\frac{1}{2}$ 测试。"
        result = build_paracol_content(md, [])
        assert r"\dfrac" in result
        assert r"\frac" not in result

    def test_display_math_also_upgraded(self):
        from latex_generator import build_paracol_content
        md = "$$\\frac{a}{b}$$"
        result = build_paracol_content(md, [])
        assert r"\dfrac" in result

    def test_non_frac_unchanged(self):
        from latex_generator import build_paracol_content
        md = "$x^2 + y^2 = z^2$"
        result = build_paracol_content(md, [])
        assert "$x^2 + y^2 = z^2$" in result


class TestLatexEscaping:
    def test_ampersand_escaped(self):
        from latex_generator import build_paracol_content
        md = "A & B 是两个选项。"
        result = build_paracol_content(md, [])
        assert r"\&" in result

    def test_percent_escaped(self):
        from latex_generator import build_paracol_content
        md = "完成率 80% 以上。"
        result = build_paracol_content(md, [])
        assert r"80\%" in result

    def test_math_mode_preserved(self):
        from latex_generator import build_paracol_content
        md = "公式 $E=mc^2$ 是正确的。"
        result = build_paracol_content(md, [])
        assert "$E=mc^2$" in result

    def test_display_math_preserved(self):
        from latex_generator import build_paracol_content
        md = "$$F = ma$$\n其中 F 为力。"
        result = build_paracol_content(md, [])
        assert "$$F = ma$$" in result


class TestImageHandling:
    def test_markdown_image_to_includegraphics(self):
        from latex_generator import build_paracol_content
        md = "如图所示：![](images/fig1.png)"
        result = build_paracol_content(md, [])
        assert r"\includegraphics" in result
        assert "fig1.png" in result


class TestNoCorrections:
    def test_no_corrections_clean(self):
        from latex_generator import build_paracol_content
        md = "这是一段没有问题的文字。公式 $x=1$ 正确。"
        result = build_paracol_content(md, [])
        assert "这是一段没有问题的文字" in result
        assert r"\textsuperscript" not in result


class TestFullPipeline:
    def test_generate_tex_creates_valid_file(self):
        from latex_generator import generate_tex

        md_content = "测试内容。公式 $F=ma$。"
        corrections = {"corrections": []}
        json_path = _write_temp_json(corrections)
        md_path = _write_temp_md(md_content)
        tex_path = os.path.join(tempfile.mkdtemp(), "output.tex")

        try:
            result = generate_tex(json_path, md_path, tex_path)
            assert result == tex_path
            assert os.path.isfile(tex_path)
            with open(tex_path, "r", encoding="utf-8") as f:
                content = f.read()
            assert r"\begin{paracol}" in content
        finally:
            os.unlink(json_path)
            os.unlink(md_path)

    def test_generated_tex_compiles_to_pdf(self):
        from latex_generator import generate_tex

        md_content = r"""**例1** 一辆汽车以初速度 $v_0 = 10\,\text{m/s}$ 行驶。

解答：（1）由速度公式得 $v_3 = 16\,\text{m/s}$。"""
        corrections = {
            "corrections": [
                {"type": "text", "original": "速度公式",
                 "correction": "匀变速直线运动速度公式", "reason": "应写明公式名称"}
            ]
        }
        json_path = _write_temp_json(corrections)
        md_path = _write_temp_md(md_content)
        tex_path = os.path.join(tempfile.mkdtemp(), "pipeline_test.tex")

        try:
            generate_tex(json_path, md_path, tex_path)
            pdf_path = compile_to_pdf(tex_path)
            assert os.path.isfile(pdf_path)
            assert os.path.getsize(pdf_path) > 0
        finally:
            os.unlink(json_path)
            os.unlink(md_path)
