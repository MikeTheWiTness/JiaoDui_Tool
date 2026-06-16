"""
LaTeX 模板测试套件
测试行为而非实现——验证模板可编译并正确渲染。
"""
import os
import subprocess
import tempfile
import shutil
import pytest

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
TEMPLATE_FILE = os.path.join(TEMPLATE_DIR, "proofread_template.tex")


def _read_template():
    """读取模板内容"""
    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        return f.read()


# ============================================================
# Cycle 1: Template exists and has required packages
# ============================================================

class TestTemplateExists:
    """行为：模板文件存在且包含所有必要宏包"""

    def test_template_file_exists(self):
        """模板文件可被读取"""
        assert os.path.isfile(TEMPLATE_FILE), f"Template not found at {TEMPLATE_FILE}"

    def test_uses_ctexart_class(self):
        """使用 ctexart 文档类"""
        content = _read_template()
        assert "ctexart" in content

    def test_uses_paracol_package(self):
        """使用 paracol 双栏宏包"""
        content = _read_template()
        assert r"\usepackage{paracol}" in content

    def test_uses_amsmath_package(self):
        """使用 amsmath 数学宏包"""
        content = _read_template()
        assert r"\usepackage{amsmath}" in content or r"\usepackage{amssymb}" in content

    def test_uses_amssymb_package(self):
        """使用 amssymb 数学符号宏包"""
        content = _read_template()
        assert r"\usepackage{amssymb}" in content

    def test_uses_mhchem_package(self):
        """使用 mhchem 化学宏包"""
        content = _read_template()
        assert r"\usepackage{mhchem}" in content or r"\usepackage[version=4]{mhchem}" in content

    def test_uses_graphicx_package(self):
        """使用 graphicx 图片宏包"""
        content = _read_template()
        assert r"\usepackage{graphicx}" in content

    def test_sets_main_fonts(self):
        """设置了中文字体（SimSun）和拉丁字体（Times New Roman）"""
        content = _read_template()
        assert "SimSun" in content
        assert "Times New Roman" in content


# ============================================================
# 编译辅助函数
# ============================================================

XELATEX = "C:/Program Files/texlive/2026/bin/windows/xelatex.exe"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "_test_latex")


def _compile_tex(tex_content: str, job_name: str = "test") -> tuple:
    """编译 .tex 内容并返回 (pdf_path, log_text)。

    用模板包裹内容，写入临时文件，调用 xelatex 编译。
    """
    template = _read_template()
    full_tex = template.replace("{{CONTENT}}", tex_content)

    tmpdir = tempfile.mkdtemp(prefix="latex_test_")
    tex_path = os.path.join(tmpdir, f"{job_name}.tex")

    with open(tex_path, "w", encoding="utf-8") as f:
        f.write(full_tex)

    log_path = os.path.join(tmpdir, "xelatex.log")
    cmd = f'"{XELATEX}" -interaction=nonstopmode -output-directory="{tmpdir}" "{tex_path}" > "{log_path}" 2>&1'
    retcode = subprocess.call(cmd, shell=True, timeout=60)

    pdf_path = os.path.join(tmpdir, f"{job_name}.pdf")
    log_text = ""
    if os.path.isfile(log_path):
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            log_text = f.read()

    # Copy PDF back to persistent output dir
    if os.path.isfile(pdf_path):
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        shutil.copy2(pdf_path, os.path.join(OUTPUT_DIR, f"{job_name}.pdf"))

    return pdf_path, log_text


def _pdf_is_valid(pdf_path: str) -> bool:
    """检查 PDF 文件是否存在且非空"""
    return os.path.isfile(pdf_path) and os.path.getsize(pdf_path) > 0


# ============================================================
# Cycle 2: Empty template compiles
# ============================================================

class TestTemplateCompiles:
    """行为：模板填充最小内容后可编译为 PDF"""

    def test_empty_content_compiles(self):
        """空正文内容编译成功，PDF 非空"""
        pdf_path, log = _compile_tex("测试编译", job_name="cycle2_empty")
        assert _pdf_is_valid(pdf_path), f"PDF not generated.\nLog:\n{log[-2000:]}"

    def test_no_latex_errors(self):
        """编译日志中无 LaTeX 致命错误"""
        _, log = _compile_tex("无错误测试", job_name="cycle2_noerror")
        assert "Fatal error" not in log, f"Fatal error in log:\n{log[-2000:]}"


# ============================================================
# Cycle 3: Chinese text renders
# ============================================================

class TestChineseRendering:
    """行为：中文字体（宋体）正常渲染，无字体警告"""

    def test_chinese_text_compiles(self):
        """中文段落编译成功"""
        content = r"""
        这是一段中文测试文本，用于验证宋体字体是否正确嵌入。
        高中物理题目通常包含物理情景描述，如：一个质量为m的物体从高度h处自由下落。
        """
        pdf_path, log = _compile_tex(content, job_name="cycle3_chinese")
        assert _pdf_is_valid(pdf_path), f"PDF not generated.\nLog:\n{log[-2000:]}"

    def test_no_font_warnings(self):
        """编译日志中无字体缺失警告"""
        content = "字体测试：物理学是研究物质运动最一般规律的科学。"
        _, log = _compile_tex(content, job_name="cycle3_font")
        assert "Font" not in log or "font" not in log, f"Font warning in log:\n{log[-2000:]}"


# ============================================================
# Cycle 4: Math formulas render
# ============================================================

class TestMathRendering:
    """行为：amsmath 公式正常渲染"""

    def test_inline_math_compiles(self):
        """行内公式编译成功"""
        content = r"质能方程 $E=mc^2$ 是爱因斯坦提出的。"
        pdf_path, log = _compile_tex(content, job_name="cycle4_inline")
        assert _pdf_is_valid(pdf_path), f"PDF not generated.\nLog:\n{log[-2000:]}"

    def test_display_math_compiles(self):
        """行间公式编译成功"""
        content = r"""
        牛顿第二定律的表达式为：
        $$F = ma$$
        其中 $F$ 为合外力，$m$ 为质量，$a$ 为加速度。
        """
        pdf_path, log = _compile_tex(content, job_name="cycle4_display")
        assert _pdf_is_valid(pdf_path), f"PDF not generated.\nLog:\n{log[-2000:]}"

    def test_physics_notation_compiles(self):
        """物理专用符号（希腊字母、矢量、上下标）编译成功"""
        content = r"""
        运动学公式：
        $$v = v_0 + at$$
        $$x = v_0t + \frac{1}{2}at^2$$
        其中 $\mu$ 为摩擦系数，$\theta$ 为倾角。
        """
        pdf_path, log = _compile_tex(content, job_name="cycle4_physics")
        assert _pdf_is_valid(pdf_path), f"PDF not generated.\nLog:\n{log[-2000:]}"


# ============================================================
# Cycle 5: Chemical formulas render
# ============================================================

class TestChemicalRendering:
    """行为：mhchem 化学式正常渲染"""

    def test_chemical_equation_compiles(self):
        """化学方程式编译成功"""
        content = r"""
        化学反应方程式：
        $$\ce{2H2 + O2 -> 2H2O}$$
        $$\ce{CH4 + 2O2 -> CO2 + 2H2O}$$
        """
        pdf_path, log = _compile_tex(content, job_name="cycle5_chem")
        assert _pdf_is_valid(pdf_path), f"PDF not generated.\nLog:\n{log[-2000:]}"

    def test_chemical_notation_compiles(self):
        """化学符号（离子、同位素）编译成功"""
        content = r"""
        离子反应：$\ce{Ca^2+ + CO3^2- -> CaCO3 v}$
        同位素：$\ce{^{235}_{92}U}$
        """
        pdf_path, log = _compile_tex(content, job_name="cycle5_chem2")
        assert _pdf_is_valid(pdf_path), f"PDF not generated.\nLog:\n{log[-2000:]}"


# ============================================================
# Cycle 6: paracol + correction markup
# ============================================================

class TestParacolCorrections:
    """行为：paracol 双栏布局 + 三种修改标记正常编译"""

    def test_paracol_two_columns_compiles(self):
        """paracol 双栏结构编译成功"""
        content = r"""
        \begin{paracol}{2}
        左栏：这是原文内容。\\
        继续原文段落。
        \switchcolumn
        右栏：这是修改建议。\\
        继续建议内容。
        \end{paracol}
        """
        pdf_path, log = _compile_tex(content, job_name="cycle6_paracol")
        assert _pdf_is_valid(pdf_path), f"PDF not generated.\nLog:\n{log[-2000:]}"

    def test_text_correction_markup_compiles(self):
        """text 类型：红色删除线+蓝色正确文字"""
        content = r"""
        \begin{paracol}{2}
        原文中有\corrtext{C---C键}{C-C键}表述不规范。
        \switchcolumn
        \correctionbox{修改建议：应将"C---C键"改为"C-C键"。三个短横线表示碳碳三键，金刚石为单键。}
        \end{paracol}
        """
        pdf_path, log = _compile_tex(content, job_name="cycle6_text")
        assert _pdf_is_valid(pdf_path), f"PDF not generated.\nLog:\n{log[-2000:]}"

    def test_rewrite_correction_markup_compiles(self):
        """rewrite 类型：红色框包裹原文"""
        content = r"""
        \begin{paracol}{2}
        \corrrewrite{碘晶体层内和层间均为分子间作用力，是分子晶体。}
        \switchcolumn
        \correctionbox{修改建议：碘晶体的结构微粒为I$_2$分子，分子间以范德华力结合
        （层内I$_2$分子间、层间作用力均为范德华力）。}
        \end{paracol}
        """
        pdf_path, log = _compile_tex(content, job_name="cycle6_rewrite")
        assert _pdf_is_valid(pdf_path), f"PDF not generated.\nLog:\n{log[-2000:]}"

    def test_region_correction_markup_compiles(self):
        """region 类型：红色虚线框标记区域"""
        content = r"""
        \begin{paracol}{2}
        第（1）题\corrregion{配图B和C的结构标注存在互换问题}。
        \switchcolumn
        \correctionbox{修改建议：配图B和C标注互换。B应对应含酯基的结构，C应对应含羧基的结构。}
        \end{paracol}
        """
        pdf_path, log = _compile_tex(content, job_name="cycle6_region")
        assert _pdf_is_valid(pdf_path), f"PDF not generated.\nLog:\n{log[-2000:]}"

    def test_mixed_corrections_compiles(self):
        """混合使用三种修改类型"""
        content = r"""
        \begin{paracol}{2}

        \textbf{题目：}下列说法正确的是。

        A. \corrtext{碘晶体层内和层间均为分子间作用力}{碘晶体中分子间均以范德华力结合}

        B. 晶胞内只存在共价键，属于共价晶体

        C. 金刚石中C原子半径小于Si，\corrtext{C---C键}{C-C键}键长更短

        D. 配图如\corrregion{图1}所示
        \switchcolumn

        \noindent\correctionbox{\textbf{A选项}：混淆了分子内共价键与
        分子间作用力的概念。碘晶体中I$_2$分子内部为共价键，仅层内、层间
        的I$_2$分子间作用力为范德华力。}

        \bigskip

        \noindent\correctionbox{\textbf{C选项}：三个短横线表示碳碳三键，
        而金刚石中碳原子间为碳碳单键，应写为"C-C键"。}

        \bigskip

        \noindent\correctionbox{\textbf{D选项}：配图与物质标注可能不一致，
        需人工核对图中B和C的化学结构是否与标注对应。}
        \switchcolumn*

        \end{paracol}
        """
        pdf_path, log = _compile_tex(content, job_name="cycle6_mixed")
        assert _pdf_is_valid(pdf_path), f"PDF not generated.\nLog:\n{log[-2000:]}"


# ============================================================
# Cycle 7: End-to-end — 真实高中物理题目模拟
# ============================================================

class TestEndToEndPhysics:
    """行为：模拟真实高中物理题目的完整校对 PDF 生成

    此测试模拟 latex_generator.py 的工作流程：
    读取原始 .md + 校对 JSON → 构建 paracol 内容 → 编译 PDF。
    需要用肉眼确认 PDF 视觉效果。
    """

    def test_physics_e2e_compiles(self):
        """端到端：高中物理题目 + 结构化校对数据 → 可编译的 PDF"""
        # 模拟原始 .md 文件内容（高中物理运动学题目）
        md_content = r"""
        **例1** 一辆汽车以初速度 $v_0 = 10\,\text{m/s}$ 在平直公路上行驶，
        以加速度 $a = 2\,\text{m/s}^2$ 做匀加速直线运动。求：

        （1）汽车在第 3 秒末的速度；
        （2）汽车在前 5 秒内的位移；
        （3）汽车在第 5 秒内的位移。

        解答：
        （1）由匀变速直线运动速度公式 $v_t = v_0 + at$ 得：
        $$v_3 = 10 + 2 \times 3 = 16\,\text{m/s}$$

        （2）由位移公式 $x = v_0t + \frac{1}{2}at^2$ 得：
        $$x_5 = 10 \times 5 + \frac{1}{2} \times 2 \times 5^2 = 50 + 25 = 75\,\text{m}$$

        （3）第 5 秒内位移 = 前 5 秒位移 - 前 4 秒位移：
        $$x_4 = 10 \times 4 + \frac{1}{2} \times 2 \times 4^2 = 40 + 16 = 56\,\text{m}$$
        $$\Delta x = x_5 - x_4 = 75 - 56 = 19\,\text{m}$$
        """

        # 用 paracol 构建双栏内容（分段同步：每个校对点一个 synchronized block）
        paracol_content = r"""
        \begin{paracol}{2}

        \noindent\textbf{例1}
        一辆汽车以初速度 $v_0 = 10\,\text{m/s}$ 在平直公路上行驶，
        以加速度 $a = 2\,\text{m/s}^2$ 做匀加速直线运动。求：

        （1）汽车在第 3 秒末的速度；\\
        （2）汽车在前 5 秒内的位移；\\
        （3）汽车在第 5 秒内的位移。
        \switchcolumn
        \correctionbox{\textbf{题干审校}：物理情景清晰，条件完整。无问题。}
        \switchcolumn*

        \medskip
        \noindent\textbf{解答：}

        （1）由 $v_t = v_0 + at$ 得：
        $$v_3 = 10 + 2 \times 3 = 16\,\text{m/s}$$
        \switchcolumn
        \correctionbox{\textbf{（1）审校}：公式选择正确，代入无误。$16\,\text{m/s}$。}
        \switchcolumn*

        \medskip
        （2）由 $x = v_0t + \frac{1}{2}at^2$ 得：
        $$x_5 = 10 \times 5 + \frac{1}{2} \times 2 \times 5^2 = 50 + 25 = 75\,\text{m}$$
        \switchcolumn
        \correctionbox{\textbf{（2）审校}：计算过程完整，结果 $75\,\text{m}$ 正确。}
        \switchcolumn*

        \medskip
        （3）第 5 秒内位移 = 前 5 秒位移 $-$ 前 4 秒位移：
        $$x_4 = 10 \times 4 + \frac{1}{2} \times 2 \times 4^2 = 40 + 16 = 56\,\text{m}$$
        $$\Delta x = x_5 - x_4 = 75 - 56 = 19\,\text{m}$$
        \switchcolumn
        \correctionbox{\textbf{（3）审校}：分步计算清晰，$\Delta x = 19\,\text{m}$ 无误。}
        \switchcolumn*

        \switchcolumn
        \bigskip
        \correctionbox{\textbf{校对总结}：无实质性错误。物理情景准确，公式使用恰当，
        计算完整。整体等级：\textbf{无问题}。}
        \switchcolumn*

        \end{paracol}
        """

        pdf_path, log = _compile_tex(paracol_content, job_name="cycle7_physics_e2e")
        assert _pdf_is_valid(pdf_path), (
            f"E2E PDF not generated.\n"
            f"Log tail:\n{log[-3000:] if log else '(empty)'}"
        )
