"""
LaTeX → PDF 编译模块
调用 xelatex 编译 .tex 文件，处理错误和清理辅助文件。
"""
import os
import shlex
import shutil
import subprocess
import tempfile

XELATEX = "C:/Program Files/texlive/2026/bin/windows/xelatex.exe"


def compile_to_pdf(tex_path: str, output_dir: str | None = None,
                   images_map: dict | None = None) -> str:
    """编译 .tex 文件为 PDF。

    在临时目录（ASCII 路径）编译以避免 xelatex 对中文路径的兼容问题，
    然后将 PDF 复制到目标 output_dir。

    Args:
        tex_path: .tex 文件路径
        output_dir: PDF 输出目录，默认为 .tex 同目录
        images_map: {section_title: {filename: source_path}} 图片映射，直接复制到临时目录

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
    base = os.path.splitext(os.path.basename(tex_path))[0]
    target_pdf = os.path.join(output_dir, f"{base}.pdf")

    # 创建临时目录用于编译（ASCII 路径，避免 xelatex 对中文路径的兼容问题）
    tmpdir = tempfile.mkdtemp(prefix="latex_compile_")
    tex_dir = os.path.dirname(tex_path) or "."
    tmp_tex = os.path.join(tmpdir, f"{base}.tex")

    try:
        # 复制 .tex 到临时目录
        shutil.copy2(tex_path, tmp_tex)

        # 从 images_map 直接复制图片到临时目录
        if images_map:
            for sec_title, imgs in images_map.items():
                sec_img_dir = os.path.join(tmpdir, sec_title, "images")
                os.makedirs(sec_img_dir, exist_ok=True)
                for fname, src in imgs.items():
                    shutil.copy2(src, os.path.join(sec_img_dir, fname))

        # 也复制 tex_dir 下的图片目录（兼容旧调用）
        for item in os.listdir(tex_dir):
            src = os.path.join(tex_dir, item)
            if os.path.isdir(src) and item not in (images_map or {}):
                dst = os.path.join(tmpdir, item)
                if not os.path.exists(dst):
                    shutil.copytree(src, dst)

        # 在临时目录中编译
        log_path = os.path.join(tmpdir, "_xelatex.log")
        cmd = [
            XELATEX, "-interaction=nonstopmode",
            f'-output-directory={tmpdir}', tmp_tex,
        ]
        with open(log_path, "w", encoding="utf-8", errors="replace") as log_f:
            retcode = subprocess.call(cmd, timeout=60, cwd=tmpdir, stdout=log_f, stderr=subprocess.STDOUT)

        tmp_pdf = os.path.join(tmpdir, f"{base}.pdf")

        if not os.path.isfile(tmp_pdf) and retcode != 0:
            log_tail = ""
            if os.path.isfile(log_path):
                with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                    log_text = f.read()
                error_lines = [ln for ln in log_text.splitlines() if ln.startswith("!")]
                log_tail = "\n".join(error_lines[-20:]) or log_text[-2000:]
            raise RuntimeError(f"Compilation failed.\n{log_tail}")

        # 复制 PDF 到目标目录
        shutil.copy2(tmp_pdf, target_pdf)

    finally:
        # 清理临时目录
        shutil.rmtree(tmpdir, ignore_errors=True)

    return target_pdf
