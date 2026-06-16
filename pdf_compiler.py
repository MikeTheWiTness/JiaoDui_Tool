"""
LaTeX → PDF 编译模块
调用 xelatex 编译 .tex 文件，处理错误和清理辅助文件。
"""
import os
import subprocess
import tempfile

XELATEX = "C:/Program Files/texlive/2026/bin/windows/xelatex.exe"


def compile_to_pdf(tex_path: str, output_dir: str | None = None) -> str:
    """编译 .tex 文件为 PDF。

    Args:
        tex_path: .tex 文件路径
        output_dir: PDF 输出目录，默认为 .tex 同目录

    Returns:
        生成的 PDF 文件路径

    Raises:
        FileNotFoundError: tex_path 不存在
        RuntimeError: xelatex 编译失败（含日志摘要）
    """
    if not os.path.isfile(tex_path):
        raise FileNotFoundError(f"TeX file not found: {tex_path}")

    if output_dir is None:
        output_dir = os.path.dirname(tex_path) or "."

    os.makedirs(output_dir, exist_ok=True)

    log_path = os.path.join(output_dir, "_xelatex.log")
    cmd = (
        f'"{XELATEX}" -interaction=nonstopmode '
        f'-output-directory="{output_dir}" "{tex_path}" '
        f'> "{log_path}" 2>&1'
    )
    retcode = subprocess.call(cmd, shell=True, timeout=60)

    base = os.path.splitext(os.path.basename(tex_path))[0]
    pdf_path = os.path.join(output_dir, f"{base}.pdf")

    if retcode != 0 or not os.path.isfile(pdf_path):
        log_tail = ""
        if os.path.isfile(log_path):
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                log_text = f.read()
            # 提取错误行
            error_lines = [ln for ln in log_text.splitlines() if ln.startswith("!")]
            log_tail = "\n".join(error_lines[-20:]) or log_text[-2000:]
        os.remove(log_path) if os.path.isfile(log_path) else None
        raise RuntimeError(f"Compilation failed.\n{log_tail}")

    # 清理辅助文件
    for ext in [".aux", ".log", ".out", ".toc"]:
        aux = os.path.join(output_dir, f"{base}{ext}")
        if os.path.isfile(aux):
            os.remove(aux)

    return pdf_path
