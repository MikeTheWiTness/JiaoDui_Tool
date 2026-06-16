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
    """写入临时 JSON 文件，返回路径"""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(data, tmp)
    tmp.close()
    return tmp.name


def _write_temp_md(content: str) -> str:
    """写入临时 .md 文件，返回路径"""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8")
    tmp.write(content)
    tmp.close()
    return tmp.name


# ============================================================
# Cycle 1: Module exists + basic generation
# ============================================================

class TestModuleExists:
    """行为：latex_generator 模块可导入"""

    def test_module_imports(self):
        import latex_generator
        assert hasattr(latex_generator, "generate_tex")


# ============================================================
# Cycle 2: Text type correction
# ============================================================

class TestTextCorrection:
    """行为：text 类型修改——原文中错误文字被 \corrtext 标记"""

    def test_text_correction_in_content(self):
        """原文中的错误文字被替换为 \corrtext{原}{改}"""
        from latex_generator import build_paracol_content

        md = "金刚石中C---C键键长更短。"
        corrections = [
            {"type": "text", "original": "C---C键", "correction": "C-C键", "reason": "应为单键"}
        ]
        result = build_paracol_content(md, corrections)
        assert r"\corrtext{C---C键}{C-C键}" in result

    def test_text_correction_in_right_column(self):
        """text 类型的 reason 出现在右栏"""
        from latex_generator import build_paracol_content

        md = "测试文字C---C键在这里。"
        corrections = [
            {"type": "text", "original": "C---C键", "correction": "C-C键", "reason": "符号错误"}
        ]
        result = build_paracol_content(md, corrections)
        assert "符号错误" in result

    def test_multiple_text_corrections(self):
        """多个 text 修改项全部被标记"""
        from latex_generator import build_paracol_content

        md = "甲说：E=mc2。乙说：F=ma。"
        corrections = [
            {"type": "text", "original": "mc2", "correction": "mc^2", "reason": "缺上标"},
            {"type": "text", "original": "ma", "correction": "m a", "reason": "缺空格"},
        ]
        result = build_paracol_content(md, corrections)
        assert r"\corrtext{mc2}{mc^2}" in result
        assert r"\corrtext{ma}{m a}" in result


# ============================================================
# Cycle 3: Rewrite type correction
# ============================================================

class TestRewriteCorrection:
    """行为：rewrite 类型——整段原文被 \corrrewrite 标记"""

    def test_rewrite_wraps_paragraph(self):
        """整段原文被红色框包裹"""
        from latex_generator import build_paracol_content

        md = "碘晶体层内和层间均为分子间作用力，是分子晶体。"
        corrections = [
            {"type": "rewrite", "original": "碘晶体层内和层间均为分子间作用力，是分子晶体。",
             "correction": "碘晶体中分子间以范德华力结合。", "reason": "概念混淆"}
        ]
        result = build_paracol_content(md, corrections)
        assert r"\corrrewrite{" in result

    def test_rewrite_reason_in_right_column(self):
        """rewrite 的 reason 出现在右栏"""
        from latex_generator import build_paracol_content

        md = "这是一个需要重写的段落。"
        corrections = [
            {"type": "rewrite", "original": "这是一个需要重写的段落。",
             "correction": "这是重写后的段落。", "reason": "表述不严谨"}
        ]
        result = build_paracol_content(md, corrections)
        assert "表述不严谨" in result


# ============================================================
# Cycle 4: Region type correction
# ============================================================

class TestRegionCorrection:
    """行为：region 类型——区域被 \corrregion 标记"""

    def test_region_wraps_location(self):
        """区域文本被红色虚线框标记"""
        from latex_generator import build_paracol_content

        md = "第（1）题配图如下所示。"
        corrections = [
            {"type": "region", "location": "第（1）题配图",
             "correction": "配图B和C标注互换", "reason": "标注错误"}
        ]
        result = build_paracol_content(md, corrections)
        assert r"\corrregion{" in result
        assert "第（1）题配图" in result


# ============================================================
# Cycle 5: LaTeX special character escaping
# ============================================================

class TestLatexEscaping:
    """行为：普通文本中的 LaTeX 特殊字符被转义，公式不被破坏"""

    def test_ampersand_escaped(self):
        """& 被转义为 \&"""
        from latex_generator import build_paracol_content

        md = "A & B 是两个选项。"
        corrections = []
        result = build_paracol_content(md, corrections)
        assert r"\&" in result
        # 公式中的 & 不受影响（这里没有公式，只检查原文）
        assert "A \\& B" in result or "A \\&" in result

    def test_percent_escaped(self):
        """% 被转义为 \%"""
        from latex_generator import build_paracol_content

        md = "完成率 80% 以上。"
        corrections = []
        result = build_paracol_content(md, corrections)
        assert r"80\%" in result

    def test_math_mode_preserved(self):
        """$...$ 数学公式不被转义"""
        from latex_generator import build_paracol_content

        md = "公式 $E=mc^2$ 是正确的。"
        corrections = []
        result = build_paracol_content(md, corrections)
        assert "$E=mc^2$" in result
        assert "^" in result  # 公式内的 ^ 未被转义

    def test_display_math_preserved(self):
        """$$...$$ 显示公式不被转义"""
        from latex_generator import build_paracol_content

        md = "$$F = ma$$\n其中 F 为力。"
        corrections = []
        result = build_paracol_content(md, corrections)
        assert "$$F = ma$$" in result


# ============================================================
# Cycle 6: Image handling
# ============================================================

class TestImageHandling:
    """行为：Markdown 图片转为 LaTeX \includegraphics"""

    def test_markdown_image_to_includegraphics(self):
        """![](path) → \includegraphics{path}"""
        from latex_generator import build_paracol_content

        md = "如图所示：![](images/fig1.png)"
        corrections = []
        result = build_paracol_content(md, corrections)
        assert r"\includegraphics" in result
        assert "fig1.png" in result


# ============================================================
# Cycle 7: No corrections — clean content
# ============================================================

class TestNoCorrections:
    """行为：无修改项的 .md 正常渲染，不包含修改标记"""

    def test_no_corrections_generates_clean_content(self):
        """无修改时内容正常，无不必要的修改命令"""
        from latex_generator import build_paracol_content

        md = "这是一段没有问题的文字。公式 $x=1$ 正确。"
        corrections = []
        result = build_paracol_content(md, corrections)
        assert "这是一段没有问题的文字" in result
        assert r"\corrtext" not in result
        assert r"\corrrewrite" not in result
        assert r"\corrregion" not in result


# ============================================================
# Cycle 8: Full pipeline — generate_tex + compile
# ============================================================

class TestFullPipeline:
    """行为：generate_tex 读取 JSON + .md → 写入 .tex → 可编译为 PDF"""

    def test_generate_tex_creates_valid_file(self):
        """generate_tex 创建合法 .tex 文件"""
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
            assert "测试内容" in content
        finally:
            os.unlink(json_path)
            os.unlink(md_path)

    def test_generated_tex_compiles_to_pdf(self):
        """生成的 .tex 可被 xelatex 编译为 PDF"""
        from latex_generator import generate_tex

        md_content = r"""
        **例1** 一辆汽车以初速度 $v_0 = 10\,\text{m/s}$ 行驶。

        解答：（1）由速度公式得 $v_3 = 16\,\text{m/s}$。
        """
        corrections = {
            "corrections": [
                {"type": "text", "original": "速度公式",
                 "correction": "$v_t = v_0 + at$", "reason": "应明确引用公式"}
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
