"""
代码执行沙箱模块测试

测试目标：验证 execute_verification() 的公共接口行为，
不关心内部实现细节。每个测试描述一个可观察的用户行为。
"""

import pytest


class TestBasicCalculation:
    """行为1：正常 SymPy 计算能返回正确结果"""

    def test_simple_arithmetic_returns_correct_result(self):
        """给定一个简单的算术验证请求，沙箱应返回正确的计算结果"""
        from code_sandbox import execute_verification

        request = {
            "type": "calculation",
            "target_expression": "2 + 3 * 4",
            "expected_result": 14,
        }

        result = execute_verification(request)

        assert result["success"] is True
        assert result["verified"] is True
        assert result["result"] == 14
        assert result["error"] is None
        assert isinstance(result["code"], str)
        assert len(result["code"]) > 0
        assert isinstance(result["elapsed_ms"], int)
        assert result["elapsed_ms"] >= 0


class TestDangerousOperationBlocking:
    """行为3：危险操作（文件读写、网络、os.system）被拦截"""

    def test_file_write_is_blocked(self):
        """包含文件写入操作的代码应被拦截，不实际执行"""
        from code_sandbox import execute_verification

        request = {
            "type": "calculation",
            "target_expression": "__import__('os').system('echo hacked')",
            "expected_result": 0,
        }

        result = execute_verification(request)

        assert result["success"] is False
        assert result["verified"] is None
        assert result["error"] is not None
        error_lower = result["error"].lower()
        assert "blocked" in error_lower or "forbidden" in error_lower or "dangerous" in error_lower

    def test_os_import_is_blocked(self):
        """直接导入 os 模块的代码应被拦截"""
        from code_sandbox import execute_verification

        request = {
            "type": "calculation",
            "target_expression": "import os; os.remove('important.txt')",
            "expected_result": None,
        }

        result = execute_verification(request)

        assert result["success"] is False
        assert result["error"] is not None

    def test_network_request_is_blocked(self):
        """包含网络请求的代码应被拦截"""
        from code_sandbox import execute_verification

        request = {
            "type": "calculation",
            "target_expression": "import urllib.request; urllib.request.urlopen('http://evil.com')",
            "expected_result": None,
        }

        result = execute_verification(request)

        assert result["success"] is False
        assert result["error"] is not None

    def test_exec_eval_is_blocked(self):
        """exec/eval 动态执行应被拦截"""
        from code_sandbox import execute_verification

        request = {
            "type": "calculation",
            "target_expression": "exec('import shutil; shutil.rmtree(\"/\")')",
            "expected_result": None,
        }

        result = execute_verification(request)

        assert result["success"] is False
        assert result["error"] is not None


class TestTimeoutTermination:
    """行为2：超时执行的代码被安全终止并返回结构化错误"""

    def test_slow_computation_is_terminated(self):
        """合法但极其耗时的 SymPy 计算应在超时后被终止，返回 timeout 错误"""
        from code_sandbox import execute_verification

        # factorial(500000) 是合法的 SymPy 表达式，大数阶乘计算远超2秒
        request = {
            "type": "calculation",
            "target_expression": "factorial(500000)",
            "expected_result": None,
        }

        # 使用 2 秒超时加速测试，而非默认的 30 秒
        result = execute_verification(request, timeout=2)

        assert result["success"] is False
        assert result["verified"] is None
        assert result["error"] is not None
        assert "timed out" in result["error"].lower() or "timeout" in result["error"].lower()
        assert isinstance(result["elapsed_ms"], int)
        assert result["elapsed_ms"] > 0


class TestGracefulDegradation:
    """行为4：LLM 生成无效代码时优雅降级，不崩溃"""

    def test_syntax_error_returns_structured_error(self):
        """语法错误的表达式应返回 success=False 和有用的错误信息，而非抛异常"""
        from code_sandbox import execute_verification

        request = {
            "type": "calculation",
            "target_expression": "2 +* 3",  # 非法语法
            "expected_result": None,
        }

        # 关键断言：函数本身不应抛出任何异常
        result = execute_verification(request)

        assert result["success"] is False
        assert result["verified"] is None
        assert result["error"] is not None
        assert len(result["error"]) > 0  # 错误信息不应为空
        assert isinstance(result["elapsed_ms"], int)

    def test_undefined_symbol_returns_structured_error(self):
        """引用未定义符号的表达式返回符号字符串（非错误）——SymPy 将其视为未知符号"""
        from code_sandbox import execute_verification

        request = {
            "type": "calculation",
            "target_expression": "undefined_variable_xyz + 1",
            "expected_result": None,
        }

        result = execute_verification(request)

        assert result["success"] is True
        assert isinstance(result["result"], str)
        assert "undefined_variable_xyz" in result["result"]

    def test_empty_expression_returns_structured_error(self):
        """空表达式应优雅降级而非崩溃"""
        from code_sandbox import execute_verification

        request = {
            "type": "calculation",
            "target_expression": "",
            "expected_result": None,
        }

        result = execute_verification(request)

        assert result["success"] is False
        assert result["verified"] is None
        assert result["error"] is not None
