import json
import os
import subprocess
import sys
import time

from sympy_tools.safety import check_dangerous


def execute_code(code: str, timeout: int = 30) -> dict:
    """在隔离子进程中执行 SymPy 代码，返回结构化结果。

    通过 stdin 传递代码以避免 Windows 命令行长度限制和文件句柄竞争。
    """
    danger = check_dangerous(code)
    if danger:
        return {
            "success": False, "result": None,
            "error": danger, "code": code, "elapsed_ms": 0,
        }

    start = time.monotonic()
    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        # 子进程中使用受限 builtins，防止 sympify 的 eval 后门被利用
        restricted_code = (
            "import builtins, sys\n"
            "_allowed = {k:v for k,v in builtins.__dict__.items() "
            "if k not in ('exec','eval','compile','open','input','breakpoint','memoryview')}\n"
            "_allowed['__build_class__'] = __build_class__\n"
            "exec(sys.stdin.read(), {'__builtins__': _allowed, '__name__': '__main__'})\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", restricted_code],
            input=code, env=env,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout,
        )
        elapsed = int((time.monotonic() - start) * 1000)

        if proc.returncode != 0:
            return {
                "success": False, "result": None,
                "error": proc.stderr.strip() or "Unknown subprocess error",
                "code": code, "elapsed_ms": elapsed,
            }

        result = json.loads(proc.stdout.strip())
        return {
            "success": True, "result": result,
            "error": None, "code": code, "elapsed_ms": elapsed,
        }

    except subprocess.TimeoutExpired:
        elapsed = int((time.monotonic() - start) * 1000)
        return {
            "success": False, "result": None,
            "error": f"Execution timed out ({timeout}s)",
            "code": code, "elapsed_ms": elapsed,
        }
    except Exception as e:
        elapsed = int((time.monotonic() - start) * 1000)
        return {
            "success": False, "result": None,
            "error": str(e), "code": code, "elapsed_ms": elapsed,
        }
