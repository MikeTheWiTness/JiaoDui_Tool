"""后处理清理管线测试 —— 覆盖 Pandoc 转换后的所有纯文本清理逻辑"""
import importlib.util
import os
import re
import pytest


# ========================= 模块加载 =========================

def _load_main_module():
    """安全加载校对工具整合版v1.7.py——不触发GUI"""
    spec = importlib.util.spec_from_file_location(
        "main_gui",
        os.path.join(os.path.dirname(__file__), "..", "校对工具整合版v1.7.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_main_module()
comprehensive_clean = _mod.comprehensive_clean
fix_pandoc_comment_anomaly = _mod.fix_pandoc_comment_anomaly
fix_tilde_in_math = _mod.fix_tilde_in_math
fix_tilde_in_text = _mod.fix_tilde_in_text
convert_italics_to_math = _mod.convert_italics_to_math
convert_display_to_inline = _mod.convert_display_to_inline
detect_answer_mode = _mod.detect_answer_mode
parse_end_answers = _mod.parse_end_answers
find_answer_section = _mod.find_answer_section
fix_floating_images = _mod.fix_floating_images
normalize_option_spacing = _mod.normalize_option_spacing
_tool_to_openai = _mod._tool_to_openai
_TOOLS_AVAILABLE = _mod._TOOLS_AVAILABLE


# ============================================================
# comprehensive_clean
# ============================================================

class TestComprehensiveClean:
    """讲义后处理：表格管道符、答案行合并、多余空格"""

    def test_removes_pipe_chars(self):
        """去除 Pandoc 表格残留的竖线"""
        r = comprehensive_clean("| 知识点 | 说明 |\n| 公式 | 推导 |")
        assert "|" not in r
        assert "知识点" in r

    def test_strips_separator_lines(self):
        """去除全部分隔符组成的行（---, ===, ::: 等）"""
        r = comprehensive_clean("标题\n-------\n内容")
        assert "---" not in r
        assert "标题" in r
        assert "内容" in r

    def test_removes_dash_equal_from_answer_line(self):
        """答案: 行去除 --- 和 === 装饰"""
        r = comprehensive_clean("答案: ---- A")
        assert r.strip() == "答案:  A"

    def test_merges_answer_with_next_letter_line(self):
        """答案: 行后紧接纯字母行则合并"""
        r = comprehensive_clean("答案:\nA")
        lines = r.split("\n")
        assert any("A" in l and "答案" in l for l in lines)

    def test_no_merge_if_non_letter(self):
        """答案: 行后不是纯字母则不合并"""
        r = comprehensive_clean("答案:\n详细解析如下")
        lines = r.split("\n")
        assert "答案:" in lines
        assert "详细解析如下" in lines

    def test_collapses_multiple_blank_lines(self):
        """3 个以上连续空行压缩为 2 个"""
        r = comprehensive_clean("第一行\n\n\n\n第二行")
        assert r.count("\n") <= 3  # 最多 第一行\n\n第二行

    def test_strips_trailing_whitespace_per_line(self):
        r = comprehensive_clean("  缩进行  ")
        assert not r.startswith(" ")
        assert not r.endswith(" ")

    def test_keeps_chinese_content_intact(self):
        original = "已知函数 $f(x)=x^2+2x+1$ 的最小值是 0。"
        r = comprehensive_clean(original)
        assert "$f(x)=x^2+2x+1$" in r

    def test_preserves_short_dash_lines(self):
        """短横线（≤2 个字符）不当作分隔线删除"""
        r = comprehensive_clean("--")
        assert "--" in r

    def test_empty_input(self):
        assert comprehensive_clean("") == ""


# ============================================================
# fix_floating_images
# ============================================================

class TestFixFloatingImages:
    """Pandoc 浮动图片修复：图片错位到 A. 选项行"""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.tmp = tmp_path

    def _write_md(self, content):
        p = self.tmp / "test.md"
        p.write_text(content, encoding="utf-8")
        return str(p)

    def test_fixes_single_float_to_A(self):
        """A. ![test](img.png) 选项文字 → 图片独立行 + A 行保留文字"""
        content = "A. ![test](img.png) 选项文字\nB. 其他选项\n"
        path = self._write_md(content)
        assert fix_floating_images(path) is True
        fixed = open(path, "r", encoding="utf-8").read()
        lines = fixed.split("\n")
        assert "![]" in lines[0]  # 图片独立成第一行
        assert "A." in lines[1]   # A 行在图片之后

    def test_skips_graphic_questions_with_B_images(self):
        """B 行也有图片的是图形题，不修复"""
        content = "A. ![test](a.png) 选项\nB. ![test](b.png) 选项\n"
        path = self._write_md(content)
        assert fix_floating_images(path) is False
        fixed = open(path, "r", encoding="utf-8").read()
        assert "A. !" in fixed  # A 行保持原样

    def test_no_float_image_no_change(self):
        content = "A. 普通选项\nB. 普通选项\nC. 普通选项\n"
        path = self._write_md(content)
        assert fix_floating_images(path) is False
        assert open(path, "r", encoding="utf-8").read() == content

    def test_A_line_without_option_text_kept(self):
        """A. ![test](img.png) 无后续文字也不报错"""
        content = "A. ![test](img.png)\nB. 选项\n"
        path = self._write_md(content)
        fix_floating_images(path)  # 不抛异常即可

    def test_image_attrs_preserved(self):
        """图片属性 {width=...} 保留"""
        content = 'A. ![test](img.png){width="3cm"} 文字\nB. 选项\n'
        path = self._write_md(content)
        assert fix_floating_images(path) is True
        fixed = open(path, "r", encoding="utf-8").read()
        assert "width" in fixed


# ============================================================
# normalize_option_spacing
# ============================================================

class TestNormalizeOptionSpacing:
    """多余空格压缩：4+ 连续空格 → 2 空格"""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.tmp = tmp_path

    def _write_md(self, content):
        p = self.tmp / "test.md"
        p.write_text(content, encoding="utf-8")
        return str(p)

    def test_compresses_4plus_spaces(self):
        content = f"A.  {' ' * 20}选项文字"
        path = self._write_md(content)
        assert normalize_option_spacing(path) is True
        fixed = open(path, "r", encoding="utf-8").read()
        assert "    " not in fixed  # 无 4+ 空格

    def test_preserves_2_spaces(self):
        content = "A.  选项"
        path = self._write_md(content)
        assert normalize_option_spacing(path) is False  # 无需修改

    def test_compresses_multiple_lines(self):
        content = f"A. {' ' * 10}内容\nB. {' ' * 15}选项"
        path = self._write_md(content)
        assert normalize_option_spacing(path) is True
        fixed = open(path, "r", encoding="utf-8").read()
        assert "    " not in fixed


# ============================================================
# 组卷网后处理
# ============================================================

class TestFixPandocCommentAnomaly:
    """去除 Pandoc HTML 注释工件"""

    def test_removes_comment_anomaly(self):
        r = fix_pandoc_comment_anomaly("文字`<!-- -->`{=html}继续")
        assert "`<!-- -->`{=html}" not in r
        assert "文字继续" in r

    def test_no_change_if_absent(self):
        content = "普通Markdown内容"
        assert fix_pandoc_comment_anomaly(content) == content


class TestFixTildeInMath:
    r"""数学模式内 \~ → \sim"""

    def test_fixes_in_inline_math(self):
        r = fix_tilde_in_math(r"$\~x$")
        assert r"\sim" in r
        assert r"\~" not in r

    def test_fixes_in_display_math(self):
        r = fix_tilde_in_math(r"$$\~{abc}$$")
        assert r"\sim" in r

    def test_preserves_math_content(self):
        r = fix_tilde_in_math(r"$a + b = c$")
        assert r"$a + b = c$" in r


class TestFixTildeInText:
    r"""文本模式 \~ → ~"""

    def test_converts_text_tilde(self):
        r = fix_tilde_in_text(r"大约\~3米")
        assert r"\~" not in r
        assert "~" in r

    def test_empty_string(self):
        assert fix_tilde_in_text("") == ""


class TestConvertItalicsToMath:
    """*italic* → $...$，保护数学块"""

    def test_single_italic(self):
        r = convert_italics_to_math("*italic*")
        assert "$italic$" in r
        assert "*italic*" not in r

    def test_protects_math_blocks(self):
        r = convert_italics_to_math("$a*b$ 和 *italic*")
        assert "$a*b$" in r  # 数学块内的 * 保留
        assert "$italic$" in r

    def test_protects_display_math(self):
        r = convert_italics_to_math("$$a*b*c$$ *x*")
        assert "$$a*b*c$$" in r
        assert "$x$" in r

    def test_italic_with_sub(self):
        """*x~i~* → $x_{i}$"""
        r = convert_italics_to_math("*x~i~*")
        assert r"$x_{i}$" in r

    def test_no_double_italic(self):
        """**bold** 不当作斜体处理"""
        content = "**bold text**"
        r = convert_italics_to_math(content)
        assert "**bold text**" in r

    def test_italic_with_chinese(self):
        r = convert_italics_to_math("方向*水平向右*的力")
        assert "$水平向右$" in r


class TestConvertDisplayToInline:
    """单行 $$...$$ → $...$，多行保留"""

    def test_single_line_to_inline(self):
        r = convert_display_to_inline("$$E=mc^2$$")
        assert r"$E=mc^2$" in r
        assert "$$" not in r

    def test_multiline_preserved(self):
        ml = "$$\na + b\n= c\n$$"
        r = convert_display_to_inline(ml)
        assert "$$" in r  # 多行公式保留 $$ 包裹
        assert "a + b" in r

    def test_no_display_math_unchanged(self):
        assert convert_display_to_inline("text") == "text"


# ============================================================
# 答案检测
# ============================================================

class TestFindAnswerSection:
    """定位参考答案章节"""

    def test_finds_bold_answer_section(self):
        lines = ["题目内容", "**参考答案**", "1. A"]
        idx, ans_lines = find_answer_section(lines)
        assert idx == 1
        assert "参考答案" in ans_lines[0]

    def test_finds_answer_with_book_title(self):
        """《...》参考答案 也是有效标记"""
        lines = ["题目", "《高中数学》参考答案", "1. B"]
        idx, ans_lines = find_answer_section(lines)
        assert idx == 1

    def test_not_found_returns_none(self):
        lines = ["题目1", "题目2", "题目3"]
        idx, ans_lines = find_answer_section(lines)
        assert idx is None
        assert ans_lines == []

    def test_empty_lines(self):
        assert find_answer_section([]) == (None, [])


class TestDetectAnswerMode:
    """检测答案模式：inline vs end"""

    def test_detects_inline_when_most_blocks_have_answer(self):
        lines = [
            "1．题目内容",
            "【答案】A",
            "2．题目内容",
            "【答案】B",
        ]
        assert detect_answer_mode(lines) == "inline"

    def test_detects_end_when_no_inline_answers(self):
        lines = [
            "1．题目内容",
            "2．题目内容",
            "**参考答案**",
            "1. A 2. B",
        ]
        assert detect_answer_mode(lines) == "end"

    def test_no_question_blocks_falls_to_end(self):
        """没有识别到题目块 → end"""
        lines = ["纯文本", "无题号"]
        assert detect_answer_mode(lines) == "end"

    def test_no_answer_section_no_question_numbers(self):
        """无参考答案且无题号 → end"""
        assert detect_answer_mode([]) == "end"


class TestParseEndAnswers:
    """解析末尾答案列表"""

    def test_parses_numbered_answers(self):
        lines = ["1. A", "【答案】A", "【详解】解析内容", "2. B", "【答案】B", "【详解】解析2"]
        result = parse_end_answers(lines)
        assert 1 in result
        assert result[1]["answer"] == "A"
        assert "解析内容" in "".join(result[1]["explanation"])
        assert 2 in result
        assert result[2]["answer"] == "B"

    def test_auto_injects_answer_when_missing(self):
        """详解前无【答案】时自动注入"""
        lines = ["1. A", "【详解】解析"]
        result = parse_end_answers(lines)
        assert "【答案】A" in result[1]["explanation"][0]

    def test_fullwidth_dot_pattern(self):
        """全角句点 1． 也匹配"""
        lines = ["1．C", "【答案】C"]
        result = parse_end_answers(lines)
        assert result[1]["answer"] == "C"

    def test_skips_non_matching_prefix(self):
        lines = ["前言说明", "1. A", "【答案】A"]
        result = parse_end_answers(lines)
        assert 1 in result

    def test_empty_input(self):
        assert parse_end_answers([]) == {}

    def test_no_numbered_lines(self):
        assert parse_end_answers(["纯文本", "无题号"]) == {}

    def test_答案_in_explanation_detected(self):
        """详解行中包含【答案】不会被重复处理"""
        lines = ["1. D", "【答案】D", "见解析"]
        result = parse_end_answers(lines)
        assert result[1]["answer"] == "D"
        # 已有的【答案】不会被自动注入覆盖
        assert "【答案】" in result[1]["explanation"][0]


# ============================================================
# _tool_to_openai
# ============================================================

@pytest.mark.skipif(not _TOOLS_AVAILABLE, reason="sympy_tools 未安装")
class TestToolToOpenai:
    """LangChain 工具 → OpenAI function-calling 格式"""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from sympy_tools.tools import EvaluateExpressionTool
        self.tool = EvaluateExpressionTool()

    def test_returns_correct_structure(self):
        result = _tool_to_openai(self.tool)
        assert result["type"] == "function"
        assert "function" in result
        func = result["function"]
        assert "name" in func
        assert "description" in func
        assert "parameters" in func
        assert func["parameters"]["type"] == "object"
        assert "properties" in func["parameters"]
        assert isinstance(func["parameters"]["required"], list)

    def test_name_matches_tool(self):
        result = _tool_to_openai(self.tool)
        assert result["function"]["name"] == self.tool.name


@pytest.mark.skipif(_TOOLS_AVAILABLE, reason="sympy_tools 已安装时已在上一类测试")
class TestToolToOpenaiMock:
    """_tool_to_openai mock 测试（无 sympy_tools 时）"""

    def test_with_mock_tool(self):
        class MockSchema:
            @staticmethod
            def model_json_schema():
                return {
                    "properties": {"expr": {"type": "string"}},
                    "required": ["expr"],
                }

        class MockTool:
            name = "mock_eval"
            description = "Mock tool"
            args_schema = MockSchema()

        result = _tool_to_openai(MockTool())
        assert result["type"] == "function"
        assert result["function"]["name"] == "mock_eval"
        assert result["function"]["parameters"]["required"] == ["expr"]
