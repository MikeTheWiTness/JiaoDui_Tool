import re

_DANGEROUS_PATTERNS = [
    r"\bimport\s+os\b",
    r"\bfrom\s+os\b",
    r"\b__import__\s*\(",
    r"\bos\s*\.\s*system\b",
    r"\bos\s*\.\s*popen\b",
    r"\bos\s*\.\s*remove\b",
    r"\bos\s*\.\s*rmdir\b",
    r"\bshutil\b",
    r"\bsubprocess\b",
    r"\burllib\b",
    r"\brequests\b",
    r"\bsocket\b",
    r"\bhttp\b",
    r"\bexec\s*\(",
    r"\beval\s*\(",
    r"(?<![.\w])compile\s*\(",
    r"\bopen\s*\(",
    r"\bfile\s*\(",
    r"\bwrite\s*\(",
    r"\bpathlib\b",
    r"\bctypes\b",
    r"\btempfile\b",
    r"\bpty\b",
    r"\bsignal\b",
]


def check_dangerous(code: str) -> str | None:
    """检查代码是否包含危险操作。返回 None 表示安全，否则返回错误信息。"""
    for pattern in _DANGEROUS_PATTERNS:
        if re.search(pattern, code, re.IGNORECASE):
            return f"Dangerous operation blocked: matched pattern '{pattern}'"
    return None
