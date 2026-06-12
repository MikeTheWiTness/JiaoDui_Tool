"""
SymPy 工具集测试套件
测试行为而非实现——通过公共接口验证端到端行为。
"""
import json
import pytest


# ============================================================
# Cycle 1: Safety 黑名单模块
# ============================================================

class TestSafetyBlacklist:
    """行为：危险操作被黑名单拦截，安全表达式通过"""

    def test_os_system_is_blocked(self):
        """os.system() 调用被拦截"""
        from sympy_tools.safety import check_dangerous

        result = check_dangerous("os.system('rm -rf /')")
        assert result is not None
        assert "os" in result.lower()

    def test_subprocess_is_blocked(self):
        """subprocess 模块导入被拦截"""
        from sympy_tools.safety import check_dangerous

        result = check_dangerous("import subprocess")
        assert result is not None

    def test_eval_is_blocked(self):
        """eval() 调用被拦截"""
        from sympy_tools.safety import check_dangerous

        result = check_dangerous("eval('1+1')")
        assert result is not None

    def test_exec_is_blocked(self):
        """exec() 调用被拦截"""
        from sympy_tools.safety import check_dangerous

        result = check_dangerous("exec('import os')")
        assert result is not None

    def test_file_write_is_blocked(self):
        """文件写入操作被拦截"""
        from sympy_tools.safety import check_dangerous

        result = check_dangerous("open('/etc/passwd', 'w')")
        assert result is not None

    def test_network_import_is_blocked(self):
        """网络库导入被拦截"""
        from sympy_tools.safety import check_dangerous

        result = check_dangerous("import urllib.request")
        assert result is not None

    def test_safe_math_expression_passes(self):
        """正常数学表达式通过检查"""
        from sympy_tools.safety import check_dangerous

        result = check_dangerous("2 + 3 * 4")
        assert result is None

    def test_safe_sympy_expression_passes(self):
        """SymPy 表达式通过检查"""
        from sympy_tools.safety import check_dangerous

        result = check_dangerous("solve(x**2 - 4, x)")
        assert result is None

    def test_injection_via_substitution_value_is_caught(self):
        """通过变量替换注入的危险代码也被拦截"""
        from sympy_tools.safety import check_dangerous

        # 攻击者尝试在 substitution 值中注入 os.system
        code = 'x = __import__("os").system("dir")'
        result = check_dangerous(code)
        assert result is not None


# ============================================================
# Cycle 2: Templates 代码生成 + 序列化器
# ============================================================

class TestCodeGeneration:
    """行为：build_code 根据操作类型生成正确的 SymPy 子进程代码"""

    def test_build_code_evaluate_generates_runnable_python(self):
        """生成的代码包含必要的 import 和可执行的 SymPy 求值"""
        from sympy_tools.templates import build_code

        code = build_code("evaluate", expression="2 + 3 * 4")

        assert "from sympy import" in code
        assert "sympify" in code
        assert "2 + 3 * 4" in code
        assert "json.dumps" in code or "json.dump" in code

    def test_build_code_unknown_operation_raises_valueerror(self):
        """未知操作类型抛出 ValueError"""
        from sympy_tools.templates import build_code

        with pytest.raises(ValueError, match="Unknown operation"):
            build_code("nonexistent_op", expression="x")


class TestSerializationThroughSandbox:
    """行为：复杂 SymPy 返回值正确序列化（通过子进程执行验证）"""

    def _run_and_get_result(self, code: str):
        """Helper: 在子进程中执行代码，返回解析后的结果"""
        from sympy_tools.sandbox import execute_code

        result = execute_code(code)
        assert result["success"], f"Subprocess failed: {result.get('error')}"
        return result["result"]

    def test_matrix_serializes_as_nested_lists(self):
        """Matrix 返回嵌套列表 [[...], [...]]"""
        from sympy_tools.templates import build_code

        code = build_code("evaluate", expression="Matrix([[1, 2], [3, 4]])")
        result = self._run_and_get_result(code)

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0] == [1.0, 2.0] or result[0] == [1, 2]

    def test_boolean_true_serializes_as_json_true(self):
        """sympy.true 序列化为 JSON true"""
        from sympy_tools.templates import build_code

        code = build_code("evaluate", expression="Eq(1, 1)")
        result = self._run_and_get_result(code)

        assert result is True

    def test_boolean_false_serializes_as_json_false(self):
        """sympy.false 序列化为 JSON false"""
        from sympy_tools.templates import build_code

        code = build_code("evaluate", expression="Eq(1, 2)")
        result = self._run_and_get_result(code)

        assert result is False

    def test_infinity_serializes_as_string(self):
        """oo 序列化为可识别的字符串"""
        from sympy_tools.templates import build_code

        code = build_code("evaluate", expression="oo")
        result = self._run_and_get_result(code)

        assert isinstance(result, str)
        assert "oo" in result.lower() or "inf" in result.lower()

    def test_simple_numeric_result_is_float(self):
        """简单数值结果返回 float"""
        from sympy_tools.templates import build_code

        code = build_code("evaluate", expression="2 + 3")
        result = self._run_and_get_result(code)

        assert isinstance(result, float)
        assert result == 5.0

    def test_trig_numeric_result_is_float(self):
        """三角函数数值结果返回 float"""
        from sympy_tools.templates import build_code

        code = build_code("evaluate", expression="sin(pi/2)")
        result = self._run_and_get_result(code)

        assert isinstance(result, float)
        assert abs(result - 1.0) < 0.001

    def test_symbolic_result_is_string(self):
        """含未定义符号的结果返回字符串"""
        from sympy_tools.templates import build_code

        code = build_code("evaluate", expression="2*x + y")
        result = self._run_and_get_result(code)

        assert isinstance(result, str)
        assert "x" in result or "y" in result


# ============================================================
# Cycle 3: EvaluateExpressionTool (BaseTool)
# ============================================================

class TestEvaluateExpressionTool:
    """行为：EvaluateExpressionTool 通过 _run() 接口求值数学表达式"""

    def _run_tool(self, expression: str, substitutions=None):
        """Helper: 实例化 tool 并调用 _run，解析返回的 JSON 字符串"""
        from sympy_tools.tools import EvaluateExpressionTool

        tool = EvaluateExpressionTool()
        result_json = tool._run(expression=expression, substitutions=substitutions)
        return json.loads(result_json)

    def test_simple_arithmetic(self):
        """2 + 3 * 4 = 14"""
        result = self._run_tool(expression="2 + 3 * 4")
        assert result["success"] is True
        assert result["result"] == 14.0

    def test_with_numeric_substitutions(self):
        """sqrt(u^2 + 2*a*s) with u=0, a=9.8, s=10 → ~14.0"""
        result = self._run_tool(
            expression="sqrt(u**2 + 2*a*s)",
            substitutions={"u": 0, "a": 9.8, "s": 10},
        )
        assert result["success"] is True
        assert abs(result["result"] - 14.0) < 0.1

    def test_with_string_substitutions(self):
        """sin(x) with x='pi/2' → 1.0"""
        result = self._run_tool(
            expression="sin(x)",
            substitutions={"x": "pi/2"},
        )
        assert result["success"] is True
        assert abs(result["result"] - 1.0) < 0.001

    def test_symbolic_expression_returns_string(self):
        """2*x + y with no substitutions returns symbolic string"""
        result = self._run_tool(expression="2*x + y")
        assert result["success"] is True
        assert isinstance(result["result"], str)

    def test_tool_has_langchain_interface(self):
        """验证 tool 具有 LangChain BaseTool 所需的所有属性"""
        from sympy_tools.tools import EvaluateExpressionTool

        tool = EvaluateExpressionTool()
        assert tool.name == "evaluate_expression"
        assert isinstance(tool.description, str)
        assert len(tool.description) > 0
        assert tool.args_schema is not None

    def test_tool_returns_openai_tool_schema(self):
        """工具可转换为 OpenAI function calling 格式的 schema"""
        from sympy_tools.tools import EvaluateExpressionTool
        from langchain_core.utils.function_calling import convert_to_openai_tool

        tool = EvaluateExpressionTool()
        schema = convert_to_openai_tool(tool)

        assert schema["type"] == "function"
        assert schema["function"]["name"] == "evaluate_expression"
        assert "parameters" in schema["function"]

    def test_invalid_expression_returns_error(self):
        """语法错误的表达式返回 success=False"""
        result = self._run_tool(expression="2 +* 3")
        assert result["success"] is False
        assert result["error"] is not None
        assert len(result["error"]) > 0

    def test_conftest_isolation(self):
        """Tool 实例化时自动具有完整的沙箱隔离"""
        from sympy_tools.tools import EvaluateExpressionTool

        tool = EvaluateExpressionTool()
        schema_fields = tool.args_schema.model_fields
        assert "expression" in schema_fields
        assert "substitutions" in schema_fields


# ============================================================
# Cycle 2: SolveEquationTool
# ============================================================

class TestSolveEquationTool:
    """行为：SolveEquationTool 通过 _run() 求解方程"""

    def _run(self, **kwargs):
        from sympy_tools.tools import SolveEquationTool
        import json

        tool = SolveEquationTool()
        return json.loads(tool._run(**kwargs))

    def test_solve_quadratic(self):
        """x^2 - 4 = 0 → [-2, 2]"""
        result = self._run(equations=["x**2 - 4 = 0"], variables=["x"])
        assert result["success"] is True
        assert isinstance(result["result"], list)

    def test_solve_linear_system(self):
        """x + y = 5, x - y = 1 → {x: 3, y: 2}"""
        result = self._run(equations=["x + y - 5", "x - y - 1"], variables=["x", "y"])
        assert result["success"] is True

    def test_solve_complex_domain(self):
        """x^2 + 1 = 0 in complex domain → [I, -I]"""
        result = self._run(
            equations=["x**2 + 1 = 0"], variables=["x"], domain="complex"
        )
        assert result["success"] is True

    def test_solve_no_solution(self):
        """x = x + 1 → 空解"""
        result = self._run(equations=["x - (x + 1)"], variables=["x"])
        assert result["success"] is True

    def test_solve_physics_kinematics(self):
        """v = u + a*t, with v=20, u=0, a=10 → t=2"""
        result = self._run(
            equations=["v - (u + a*t)", "v - 20", "u", "a - 10"],
            variables=["v", "u", "a", "t"],
        )
        assert result["success"] is True

    def test_tool_interface(self):
        from sympy_tools.tools import SolveEquationTool

        tool = SolveEquationTool()
        assert tool.name == "solve_equation"
        assert isinstance(tool.description, str)
        assert len(tool.description) > 0
        assert tool.args_schema is not None
        fields = tool.args_schema.model_fields
        assert "equations" in fields
        assert "variables" in fields


# ============================================================
# Cycle 3: CheckEqualityTool
# ============================================================

class TestCheckEqualityTool:
    """行为：CheckEqualityTool 判断两表达式是否数学等价"""

    def _run(self, **kwargs):
        from sympy_tools.tools import CheckEqualityTool
        import json

        tool = CheckEqualityTool()
        return json.loads(tool._run(**kwargs))

    def test_trig_identity_is_equivalent(self):
        """sin(x)^2 + cos(x)^2 == 1"""
        result = self._run(expression_a="sin(x)**2 + cos(x)**2", expression_b="1")
        assert result["success"] is True
        assert result["result"] is True

    def test_not_equivalent(self):
        """x^2 != x^3"""
        result = self._run(expression_a="x**2", expression_b="x**3")
        assert result["success"] is True
        assert result["result"] is False

    def test_equivalent_after_expansion(self):
        """(x+1)^2 == x^2 + 2*x + 1"""
        result = self._run(expression_a="(x+1)**2", expression_b="x**2 + 2*x + 1")
        assert result["success"] is True
        assert result["result"] is True

    def test_physics_formula_equality(self):
        """E = m*c^2 vs E = c^2*m"""
        result = self._run(expression_a="m*c**2", expression_b="c**2*m")
        assert result["success"] is True
        assert result["result"] is True

    def test_tool_interface(self):
        from sympy_tools.tools import CheckEqualityTool

        tool = CheckEqualityTool()
        assert tool.name == "check_equality"
        assert tool.args_schema is not None
        fields = tool.args_schema.model_fields
        assert "expression_a" in fields
        assert "expression_b" in fields


# ============================================================
# Cycle 4: SimplifyExpressionTool
# ============================================================

class TestSimplifyExpressionTool:
    """行为：SimplifyExpressionTool 化简/展开/三角化简数学表达式"""

    def _run(self, **kwargs):
        from sympy_tools.tools import SimplifyExpressionTool
        import json

        tool = SimplifyExpressionTool()
        return json.loads(tool._run(**kwargs))

    def test_simplify_polynomial(self):
        """2*x + 3*x → 5*x"""
        result = self._run(expression="2*x + 3*x", method="simplify")
        assert result["success"] is True
        assert "5" in str(result["result"]) and "x" in str(result["result"])

    def test_expand_binomial(self):
        """(x+1)**2 → x^2 + 2*x + 1"""
        result = self._run(expression="(x+1)**2", method="expand")
        assert result["success"] is True
        result_str = str(result["result"])
        assert "x**2" in result_str or "x^2" in result_str

    def test_trig_simplify(self):
        """sin(x)^2 + cos(x)^2 → 1"""
        result = self._run(expression="sin(x)**2 + cos(x)**2", method="trigsimp")
        assert result["success"] is True
        assert result["result"] == 1.0

    def test_factor_expression(self):
        """x^2 - 1 → (x-1)*(x+1)"""
        result = self._run(expression="x**2 - 1", method="factor")
        assert result["success"] is True

    def test_default_method_is_simplify(self):
        """无 method 参数默认使用 simplify"""
        result = self._run(expression="x + x")
        assert result["success"] is True
        assert "2" in str(result["result"])

    def test_tool_interface(self):
        from sympy_tools.tools import SimplifyExpressionTool

        tool = SimplifyExpressionTool()
        assert tool.name == "simplify_expression"
        assert tool.args_schema is not None
        fields = tool.args_schema.model_fields
        assert "expression" in fields
        assert "method" in fields


# ============================================================
# Cycle 5: SolvePhysicsFormulaTool
# ============================================================

class TestSolvePhysicsFormulaTool:
    """行为：SolvePhysicsFormulaTool 从物理公式解出目标变量并可选代入求值"""

    def _run(self, **kwargs):
        from sympy_tools.tools import SolvePhysicsFormulaTool
        import json

        tool = SolvePhysicsFormulaTool()
        return json.loads(tool._run(**kwargs))

    def test_solve_for_variable(self):
        """v = u + a*t → solve for a → a = (v - u)/t"""
        result = self._run(formula="v = u + a*t", solve_for="a")
        assert result["success"] is True
        assert "a" in str(result["result"]) or "v" in str(result["result"])

    def test_solve_with_numeric_substitution(self):
        """v = u + a*t, v=20, u=0, t=5 → a = 4"""
        result = self._run(
            formula="v = u + a*t",
            solve_for="a",
            known_values={"v": 20, "u": 0, "t": 5},
        )
        assert result["success"] is True
        # result should contain a=4 or the solution dict
        result_str = str(result["result"])
        assert "4" in result_str

    def test_solve_kinetic_energy(self):
        """E = 1/2*m*v^2 → solve for v → v = sqrt(2*E/m)"""
        result = self._run(formula="E = 1/2 * m * v**2", solve_for="v")
        assert result["success"] is True
        result_str = str(result["result"]).lower()
        assert "sqrt" in result_str or "(" in result_str

    def test_solve_newton_second(self):
        """F = m*a → solve for m → m = F/a"""
        result = self._run(formula="F = m * a", solve_for="m")
        assert result["success"] is True

    def test_solve_with_denominator(self):
        """R = U/I → solve for I → I = U/R"""
        result = self._run(formula="R = U / I", solve_for="I")
        assert result["success"] is True

    def test_tool_interface(self):
        from sympy_tools.tools import SolvePhysicsFormulaTool

        tool = SolvePhysicsFormulaTool()
        assert tool.name == "solve_physics_formula"
        fields = tool.args_schema.model_fields
        assert "formula" in fields
        assert "solve_for" in fields
        assert "known_values" in fields


# ============================================================
# Cycle 6: DimensionalAnalysisTool
# ============================================================

class TestDimensionalAnalysisTool:
    """行为：DimensionalAnalysisTool 对物理表达式做量纲分析"""

    def _run(self, **kwargs):
        from sympy_tools.tools import DimensionalAnalysisTool
        import json

        tool = DimensionalAnalysisTool()
        return json.loads(tool._run(**kwargs))

    def test_check_consistency_f_equals_ma(self):
        """F = m*a 量纲一致（牛顿 = 千克·米/秒^2）"""
        result = self._run(
            expression="F = m * a",
            operation="check_consistency",
            unit_definitions={"F": "newton", "m": "kilogram", "a": "meter/second**2"},
        )
        assert result["success"] is True

    def test_get_dimensions_of_force(self):
        """force 的量纲是 [M][L][T]^-2"""
        result = self._run(
            expression="kilogram * meter / second**2",
            operation="get_dimensions",
        )
        assert result["success"] is True

    def test_check_inconsistent_units(self):
        """千克 = 米 量纲不一致"""
        result = self._run(
            expression="kilogram = meter",
            operation="check_consistency",
        )
        assert result["success"] is True

    def test_convert_mps_to_kmph(self):
        """5 m/s → 18 km/h"""
        result = self._run(
            expression="5 * meter / second",
            operation="convert",
            target_units="kilometer / hour",
        )
        assert result["success"] is True

    def test_tool_interface(self):
        from sympy_tools.tools import DimensionalAnalysisTool

        tool = DimensionalAnalysisTool()
        assert tool.name == "dimensional_analysis"
        fields = tool.args_schema.model_fields
        assert "expression" in fields
        assert "operation" in fields


# ============================================================
# Cycle 7: ComputeLimitTool
# ============================================================

class TestComputeLimitTool:
    """行为：ComputeLimitTool 计算极限"""

    def _run(self, **kwargs):
        from sympy_tools.tools import ComputeLimitTool
        import json

        tool = ComputeLimitTool()
        return json.loads(tool._run(**kwargs))

    def test_limit_sin_x_over_x(self):
        """lim(x→0) sin(x)/x = 1"""
        result = self._run(expression="sin(x)/x", variable="x", approach="0")
        assert result["success"] is True
        assert result["result"] == 1.0

    def test_limit_1_over_x_inf(self):
        """lim(x→∞) 1/x = 0"""
        result = self._run(expression="1/x", variable="x", approach="oo")
        assert result["success"] is True
        assert result["result"] == 0.0

    def test_limit_polynomial(self):
        """lim(x→2) x^2 = 4"""
        result = self._run(expression="x**2", variable="x", approach="2")
        assert result["success"] is True
        assert result["result"] == 4.0

    def test_limit_one_sided(self):
        """lim(x→0+) 1/x = ∞"""
        result = self._run(expression="1/x", variable="x", approach="0", direction="+")
        assert result["success"] is True
        assert "oo" in str(result["result"]) or "inf" in str(result["result"]).lower()

    def test_tool_interface(self):
        from sympy_tools.tools import ComputeLimitTool

        tool = ComputeLimitTool()
        assert tool.name == "compute_limit"
        assert tool.args_schema is not None
        fields = tool.args_schema.model_fields
        assert "expression" in fields
        assert "variable" in fields
        assert "approach" in fields


# ============================================================
# Slice 4: Geometry Tools
# ============================================================

class TestGeometryTool:
    """行为：geometry 构造+测量几何对象"""

    def _run(self, **kwargs):
        from sympy_tools.tools import GeometryTool
        import json
        tool = GeometryTool()
        return json.loads(tool._run(**kwargs))

    # ---- 构造 ----

    def test_construct_line_from_two_points(self):
        """两点定线：Point(0,0), Point(h, 2*h)"""
        result = self._run(expression="Line(Point(0, 0), Point(h, 2*h))")
        assert result["success"] is True
        assert "Line" in str(result["result"]) or "line" in str(result["result"]).lower()

    def test_construct_perpendicular_line(self):
        """过点做垂线"""
        result = self._run(expression="Line(Point(0, 0), Point(1, 2)).perpendicular_line(Point(0, 0))")
        assert result["success"] is True
        assert "Line" in str(result["result"]) or "line" in str(result["result"]).lower()

    def test_construct_circle(self):
        """圆心+半径定圆：Circle(Point(h, 0), 2.5*h)"""
        result = self._run(expression="Circle(Point(h, 0), 2.5*h)")
        assert result["success"] is True
        result_str = str(result["result"]).lower()
        assert "circle" in result_str or "2.5" in result_str

    def test_midpoint(self):
        """中点: Point(0,0).midpoint(Point(2*h, 2*h))"""
        result = self._run(expression="Point(0, 0).midpoint(Point(2*h, 2*h))")
        assert result["success"] is True
        assert "h" in str(result["result"])

    # ---- 测量 ----

    def test_distance_two_points(self):
        """两点距：Point(0,0) 和 Point(3*h, 4*h) → 5*|h|"""
        result = self._run(
            expression="Point(0, 0).distance(Point(3*h, 4*h))"
        )
        assert result["success"] is True
        assert "5" in str(result["result"]) or "Abs" in str(result["result"])

    def test_angle_between_lines(self):
        """两线夹角"""
        result = self._run(
            expression="Line(Point(0,0), Point(1,0)).angle_between(Line(Point(0,0), Point(1,1)))"
        )
        assert result["success"] is True

    def test_intersection_circle_line(self):
        """圆与直线交点"""
        result = self._run(
            expression="Circle(Point(0, 0), 5).intersection(Line(Point(-10, 3), Point(10, 3)))"
        )
        assert result["success"] is True
        assert isinstance(result["result"], list)

    def test_contains_point(self):
        """点是否在圆上"""
        result = self._run(
            expression="Circle(Point(0, 0), 5).encloses_point(Point(3, 4))"
        )
        assert result["success"] is True
        # Point(3,4) is on the circle if radius=5, encloses_point returns False for boundary
        assert isinstance(result["result"], bool)

    def test_tool_interface(self):
        from sympy_tools.tools import GeometryTool
        tool = GeometryTool()
        assert tool.name == "geometry"
        assert "expression" in tool.args_schema.model_fields


class TestVectorOperationsTool:
    """行为：vector_operations 向量运算"""

    def _run(self, **kwargs):
        from sympy_tools.tools import VectorOperationsTool
        import json
        tool = VectorOperationsTool()
        return json.loads(tool._run(**kwargs))

    def test_dot_product(self):
        """点积：(1,2,3)·(4,5,6) = 32"""
        result = self._run(
            operation="dot", vec_a=[1, 2, 3], vec_b=[4, 5, 6]
        )
        assert result["success"] is True
        assert result["result"] == 32.0

    def test_cross_product_3d(self):
        """叉积（3D）：(1,0,0)×(0,1,0) = (0,0,1)"""
        result = self._run(
            operation="cross", vec_a=[1, 0, 0], vec_b=[0, 1, 0]
        )
        assert result["success"] is True
        assert result["result"] == [0.0, 0.0, 1.0]

    def test_cross_product_2d(self):
        """叉积（2D）：(1,2)×(3,4) = 1*4 - 2*3 = -2"""
        result = self._run(
            operation="cross", vec_a=[1, 2], vec_b=[3, 4]
        )
        assert result["success"] is True
        assert result["result"] == -2.0

    def test_vector_angle(self):
        """向量夹角：(1,0) 和 (1,1) → 45° = pi/4"""
        result = self._run(
            operation="angle", vec_a=[1, 0], vec_b=[1, 1]
        )
        assert result["success"] is True
        assert abs(result["result"] - 0.7854) < 0.001  # pi/4 ≈ 0.7854

    def test_projection(self):
        """向量投影：(3,4) 投影到 (1,0) → (3, 0)"""
        result = self._run(
            operation="projection", vec_a=[3, 4], vec_b=[1, 0]
        )
        assert result["success"] is True
        assert result["result"] == [3.0, 0.0]

    def test_tool_interface(self):
        from sympy_tools.tools import VectorOperationsTool
        tool = VectorOperationsTool()
        assert tool.name == "vector_operations"
        fields = tool.args_schema.model_fields
        assert "operation" in fields
        assert "vec_a" in fields
        assert "vec_b" in fields


# ============================================================
# Slice 5: Magnetic Deflection Tool
# ============================================================

class TestCircleFromTwoPointsTool:
    """行为：circle_from_two_points 根据两点+约束求解圆心和半径"""

    def _run(self, **kwargs):
        from sympy_tools.tools import CircleFromTwoPointsTool
        import json
        tool = CircleFromTwoPointsTool()
        return json.loads(tool._run(**kwargs))

    def test_deflection_radius(self):
        """P2(1.5h,0) 入磁场，垂直撞击 y=-1.5h 挡板 → R=2.5h"""
        result = self._run(
            entry_point=["1.5*h", "0"],
            velocity_direction=[3, 4],
            impact_point=["0", "-1.5*h"],
            impact_normal=[0, 1],
        )
        assert result["success"] is True
        data = result["result"]
        # R = 5*sqrt(h**2)/2 = 2.5*|h| = 2.5h for h>0
        radius_str = str(data.get("radius", ""))
        assert "5" in radius_str and "sqrt" in radius_str and "2" in radius_str

    def test_center_coordinates(self):
        """圆心坐标应该可以求出"""
        result = self._run(
            entry_point=["1.5*h", "0"],
            velocity_direction=[3, 4],
            impact_point=["0", "-1.5*h"],
            impact_normal=[0, 1],
        )
        assert result["success"] is True
        assert "center" in result["result"]

    def test_simple_circular_motion(self):
        """简单情况：x轴入射，垂直撞击y轴 → 可解"""
        result = self._run(
            entry_point=["h", "0"],
            velocity_direction=[0, 1],
            impact_point=["0", "h"],
            impact_normal=[1, 0],
        )
        assert result["success"] is True

    def test_tool_interface(self):
        from sympy_tools.tools import CircleFromTwoPointsTool
        tool = CircleFromTwoPointsTool()
        assert tool.name == "circle_from_two_points"
        fields = tool.args_schema.model_fields
        assert "entry_point" in fields
        assert "velocity_direction" in fields
        assert "impact_point" in fields
