"""
pdf_compiler 测试套件
测试行为而非实现——通过公共接口 compile_to_pdf 验证端到端编译。
"""
import os
import tempfile
import pytest


# ============================================================
# Cycle 1: Module exists + basic interface
# ============================================================

class TestModuleExists:
    """行为：pdf_compiler 模块可导入，compile_to_pdf 函数存在"""

    def test_module_imports(self):
        """模块可正常导入"""
        import pdf_compiler
        assert hasattr(pdf_compiler, "compile_to_pdf")

    def test_function_signature(self):
        """compile_to_pdf 有 tex_path 和 output_dir 参数"""
        import pdf_compiler
        import inspect
        sig = inspect.signature(pdf_compiler.compile_to_pdf)
        params = list(sig.parameters.keys())
        assert "tex_path" in params


# ============================================================
# Cycle 2: Compiles valid .tex → PDF
# ============================================================

class TestCompileValidTex:
    """行为：传入合法 .tex 文件，返回对应 PDF 路径"""

    @pytest.fixture
    def valid_tex(self):
        """创建一个最小可编译的 .tex 文件"""
        content = r"""
\documentclass{article}
\begin{document}
Hello, World!
\end{document}
"""
        tmpdir = tempfile.mkdtemp(prefix="pdfcompiler_test_")
        tex_path = os.path.join(tmpdir, "valid.tex")
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(content)
        yield tex_path
        # cleanup
        for f in os.listdir(tmpdir):
            os.remove(os.path.join(tmpdir, f))
        os.rmdir(tmpdir)

    def test_compile_returns_pdf_path(self, valid_tex):
        """编译成功返回 PDF 路径"""
        from pdf_compiler import compile_to_pdf
        pdf_path = compile_to_pdf(valid_tex)
        assert pdf_path.endswith(".pdf")
        assert os.path.isfile(pdf_path)

    def test_pdf_is_non_empty(self, valid_tex):
        """生成的 PDF 文件非空"""
        from pdf_compiler import compile_to_pdf
        pdf_path = compile_to_pdf(valid_tex)
        assert os.path.getsize(pdf_path) > 0

    def test_output_dir_parameter(self, valid_tex):
        """output_dir 参数指定 PDF 输出目录"""
        from pdf_compiler import compile_to_pdf
        custom_dir = tempfile.mkdtemp(prefix="pdfcompiler_out_")
        try:
            pdf_path = compile_to_pdf(valid_tex, output_dir=custom_dir)
            assert os.path.dirname(pdf_path) == custom_dir
            assert os.path.isfile(pdf_path)
        finally:
            for f in os.listdir(custom_dir):
                os.remove(os.path.join(custom_dir, f))
            os.rmdir(custom_dir)


# ============================================================
# Cycle 3: Invalid .tex raises error
# ============================================================

class TestCompileInvalidTex:
    """行为：非法 .tex 文件抛出 RuntimeError"""

    @pytest.fixture
    def invalid_tex(self):
        """创建一个有语法错误的 .tex 文件"""
        content = r"""
\documentclass{article}
\begin{document}
\invalidcommand
"""
        tmpdir = tempfile.mkdtemp(prefix="pdfcompiler_test_")
        tex_path = os.path.join(tmpdir, "invalid.tex")
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(content)
        yield tex_path
        for f in os.listdir(tmpdir):
            os.remove(os.path.join(tmpdir, f))
        os.rmdir(tmpdir)

    def test_invalid_tex_raises_runtime_error(self, invalid_tex):
        """语法错误的 .tex 抛出 RuntimeError"""
        from pdf_compiler import compile_to_pdf
        with pytest.raises(RuntimeError, match="[Cc]ompil"):
            compile_to_pdf(invalid_tex)

    def test_error_message_contains_log(self, invalid_tex):
        """错误消息中包含 LaTeX 日志信息"""
        from pdf_compiler import compile_to_pdf
        try:
            compile_to_pdf(invalid_tex)
        except RuntimeError as e:
            assert len(str(e)) > 50


# ============================================================
# Cycle 4: File not found
# ============================================================

class TestFileNotFound:
    """行为：传入不存在的文件抛出 FileNotFoundError"""

    def test_nonexistent_file_raises(self):
        """不存在的 .tex 文件抛出 FileNotFoundError"""
        from pdf_compiler import compile_to_pdf
        with pytest.raises(FileNotFoundError):
            compile_to_pdf("/nonexistent/path/file.tex")


# ============================================================
# Cycle 5: Cleanup auxiliary files
# ============================================================

class TestCleanup:
    """行为：编译成功后清理辅助文件"""

    def test_aux_files_cleaned_after_compile(self):
        """编译成功后 .aux .log .out 被清理"""
        from pdf_compiler import compile_to_pdf
        content = r"""
\documentclass{article}
\title{Test}
\begin{document}
\maketitle
Hello.
\end{document}
"""
        tmpdir = tempfile.mkdtemp(prefix="pdfcompiler_test_")
        tex_path = os.path.join(tmpdir, "cleanup.tex")
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(content)

        try:
            compile_to_pdf(tex_path)
            # 检查辅助文件不存在
            base = os.path.splitext(tex_path)[0]
            for ext in [".aux", ".log", ".out"]:
                assert not os.path.isfile(base + ext), f"{ext} should be cleaned"
        finally:
            for f in os.listdir(tmpdir):
                os.remove(os.path.join(tmpdir, f))
            os.rmdir(tmpdir)
