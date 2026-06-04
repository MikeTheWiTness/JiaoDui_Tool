"""
代码执行沙箱模块 (deprecated)

此模块保留用于向后兼容。新代码请使用 sympy_tools 包。
"""
import json

from sympy_tools.safety import check_dangerous as _check_dangerous
from sympy_tools.templates import build_code as _build_code
from sympy_tools.sandbox import execute_code as _execute_code

# 保留原有危险模式列表以供外部引用
from sympy_tools.safety import check_dangerous
_DANGEROUS_PATTERNS = [
    r"\bimport\s+os\b", r"\bfrom\s+os\b", r"\b__import__\s*\(",
    r"\bos\s*\.\s*system\b", r"\bos\s*\.\s*popen\b",
    r"\bos\s*\.\s*remove\b", r"\bos\s*\.\s*rmdir\b",
    r"\bshutil\b", r"\bsubprocess\b", r"\burllib\b",
    r"\brequests\b", r"\bsocket\b", r"\bhttp\b",
    r"\bexec\s*\(", r"\beval\s*\(", r"\bcompile\s*\(",
    r"\bopen\s*\(", r"\bfile\s*\(", r"\bwrite\s*\(",
    r"\bpathlib\b",
]


def execute_verification(verification_request: dict, timeout: int = 30) -> dict:
    """执行符号验证（向后兼容接口）。

    将旧格式的 verifiation_request 映射到新的 sympy_tools 执行管道。
    """
    expression = verification_request.get("target_expression", "")
    expected = verification_request.get("expected_result")

    code = _build_code("evaluate", expression=expression)
    result = _execute_code(code, timeout)

    return {
        "success": result["success"],
        "verified": result["result"] == expected if result["success"] else None,
        "result": result["result"],
        "error": result["error"],
        "code": result["code"],
        "elapsed_ms": result["elapsed_ms"],
    }
