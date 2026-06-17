"""Markdown 校对结果解析测试 — LaTeX 命令零冲突"""
import importlib.util
import os
import pytest


def _load_parser():
    spec = importlib.util.spec_from_file_location(
        "proofread_gui",
        os.path.join(os.path.dirname(__file__), "..", "API校对单讲拆分v1.7.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._parse_proofread_md


parse = _load_parser()


class TestParseBasics:
    def test_no_problems(self):
        r = parse("无问题")
        assert r["summary"] == "无问题"
        assert r["corrections"] == []

    def test_single_text_correction(self):
        r = parse("""轻微问题
### 修改 1
- **类型**: text
- **原文**: ``C---C键``
- **改为**: ``C-C键``
- **原因**: 符号错误""")
        assert r["summary"] == "轻微问题"
        assert len(r["corrections"]) == 1
        assert r["corrections"][0]["original"] == "C---C键"
        assert r["corrections"][0]["correction"] == "C-C键"

    def test_multiple_corrections(self):
        r = parse("""一般问题
### 修改 1
- **类型**: text
- **原文**: ``天工关物``
- **改为**: ``天工开物``
- **原因**: 书名错别字

### 修改 2
- **类型**: text
- **原文**: ``500N``
- **改为**: ``450N``
- **原因**: 计算错误""")
        assert len(r["corrections"]) == 2
        assert r["corrections"][1]["original"] == "500N"


class TestLaTeXCommands:
    """LaTeX 命令无冲突——反引号内任意字符均可"""

    def test_sin_command(self):
        r = parse("""轻微问题
### 修改 1
- **类型**: text
- **原文**: ``\\sin\\theta``
- **改为**: ``\\cos\\theta``
- **原因**: 正弦应为余弦""")
        assert r["corrections"][0]["original"] == "\\sin\\theta"

    def test_mathrm(self):
        r = parse("""轻微问题
### 修改 1
- **类型**: text
- **原文**: ``$\\mathrm{N}$``
- **改为**: ``$\\mathrm{n}$``
- **原因**: 单位小写""")
        assert "mathrm" in r["corrections"][0]["original"]

    def test_times(self):
        r = parse("""一般问题
### 修改 1
- **类型**: text
- **原文**: ``$2\\times 3 = 5$``
- **改为**: ``$2\\times 3 = 6$``
- **原因**: 计算结果错误""")
        assert "\\times" in r["corrections"][0]["original"]

    def test_frac(self):
        r = parse("""轻微问题
### 修改 1
- **类型**: text
- **原文**: ``$\\frac{1}{2}$``
- **改为**: ``$\\frac{1}{3}$``
- **原因**: 分母应为3""")
        assert "\\frac" in r["corrections"][0]["original"]

    def test_begin(self):
        r = parse("""轻微问题
### 修改 1
- **类型**: text
- **原文**: ``\\begin{equation}``
- **改为**: ``\\begin{align}``
- **原因**: 对齐环境更合适""")
        assert "\\begin" in r["corrections"][0]["original"]

    def test_beta_gamma(self):
        r = parse("""轻微问题
### 修改 1
- **类型**: text
- **原文**: ``\\beta\\gamma``
- **改为**: ``\\alpha\\beta``
- **原因**: 符号顺序错误""")
        assert "\\beta" in r["corrections"][0]["original"]

    def test_unit(self):
        r = parse("""轻微问题
### 修改 1
- **类型**: text
- **原文**: ``\\unit{kg.m/s^2}``
- **改为**: ``\\unit{kg.m.s^{-2}}``
- **原因**: 单位格式统一""")
        assert "\\unit" in r["corrections"][0]["original"]

    def test_underline(self):
        r = parse("""轻微问题
### 修改 1
- **类型**: text
- **原文**: ``\\underline{x}``
- **改为**: ``\\bar{x}``
- **原因**: 上划线更合适""")
        assert "\\underline" in r["corrections"][0]["original"]

    def test_all_common_commands(self):
        """一口气覆盖所有常用 LaTeX 命令"""
        cmds = [
            "\\sin", "\\cos", "\\tan", "\\cot", "\\sec", "\\csc",
            "\\arcsin", "\\arccos", "\\arctan",
            "\\log", "\\ln", "\\lg",
            "\\lim", "\\limsup", "\\liminf",
            "\\max", "\\min", "\\sup", "\\inf",
            "\\det", "\\gcd", "\\hom",
            "\\dim", "\\ker", "\\Pr",
            "\\alpha", "\\beta", "\\gamma", "\\delta", "\\epsilon",
            "\\theta", "\\lambda", "\\mu", "\\pi", "\\rho",
            "\\sigma", "\\tau", "\\phi", "\\omega",
            "\\Gamma", "\\Delta", "\\Theta", "\\Lambda", "\\Sigma", "\\Omega",
            "\\times", "\\div", "\\pm", "\\mp",
            "\\cdot", "\\star", "\\ast",
            "\\leq", "\\geq", "\\ll", "\\gg",
            "\\neq", "\\approx", "\\equiv", "\\sim", "\\simeq",
            "\\propto", "\\infty", "\\partial", "\\nabla",
            "\\forall", "\\exists", "\\neg", "\\emptyset",
            "\\in", "\\notin", "\\subset", "\\supset",
            "\\cup", "\\cap", "\\setminus",
            "\\rightarrow", "\\Rightarrow", "\\leftrightarrow",
            "\\uparrow", "\\downarrow",
            "\\sum", "\\prod", "\\int", "\\oint",
            "\\frac", "\\sqrt", "\\overline", "\\underline",
            "\\mathrm", "\\mathbf", "\\mathit", "\\mathsf", "\\mathtt",
            "\\mathcal", "\\mathbb", "\\mathfrak",
            "\\text", "\\textbf", "\\textit",
            "\\begin", "\\end",
            "\\hat", "\\tilde", "\\bar", "\\vec", "\\dot", "\\ddot",
            "\\left", "\\right", "\\big", "\\Big",
            "\\textbackslash", "\\textasciicircum", "\\textasciitilde",
        ]
        # 每 8 个命令一组生成一个修改项
        text = "一般问题\n"
        for i, cmd in enumerate(cmds):
            text += f"""### 修改 {i+1}
- **类型**: text
- **原文**: ``{cmd}{{x}}``
- **改为**: ``{cmd}{{y}}``
- **原因**: 变量名修正

"""
        r = parse(text)
        assert len(r["corrections"]) == len(cmds)
        for i, cmd in enumerate(cmds):
            assert r["corrections"][i]["original"].startswith(cmd), f"Failed for {cmd}"


class TestEdgeCases:
    def test_rewrite_type(self):
        r = parse("""严重错误
### 修改 1
- **类型**: rewrite
- **原文**: ``整段需要重写的文字``
- **改为**: ``重写后的完整文字``
- **原因**: 表述不严谨""")
        assert r["corrections"][0]["type"] == "rewrite"

    def test_region_type(self):
        r = parse("""一般问题
### 修改 1
- **类型**: region
- **位置**: ``第（1）题配图``
- **改为**: ``配图B和C标注互换``
- **原因**: 图文标注不符""")
        assert r["corrections"][0]["type"] == "region"
        assert r["corrections"][0]["location"] == "第（1）题配图"

    def test_multiline_original(self):
        r = parse("""一般问题
### 修改 1
- **类型**: text
- **原文**: ``第一行
第二行``
- **改为**: ``修正后的
两行文字``
- **原因**: 两行都需要改""")
        assert "\n" in r["corrections"][0]["original"]

    def test_dollar_math(self):
        r = parse("""轻微问题
### 修改 1
- **类型**: text
- **原文**: ``$E=mc^2$``
- **改为**: ``$E=mc^3$``
- **原因**: 指数错误""")
        assert r["corrections"][0]["original"] == "$E=mc^2$"

    def test_single_backtick_fallback(self):
        r = parse("""轻微问题
### 修改 1
- **类型**: text
- **原文**: `单反引号`
- **改为**: `单反引号修正`
- **原因**: 测试单引号回退""")
        assert r["corrections"][0]["original"] == "单反引号"

    def test_empty_input(self):
        assert parse("") is None
        assert parse("   ") is None

    def test_unparseable_text(self):
        assert parse("这是一段普通文本没有任何标记") is None
