import json
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from sympy_tools.sandbox import execute_code
from sympy_tools.templates import build_code


def _run_operation(operation: str, **params) -> str:
    """统一执行模式：build_code → execute_code → JSON string"""
    try:
        code = build_code(operation, **params)
        result = execute_code(code)
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({
            "success": False, "result": None,
            "error": str(e), "code": "", "elapsed_ms": 0,
        }, ensure_ascii=False)


# ---- EvaluateExpressionTool ----

class EvaluateParams(BaseModel):
    expression: str = Field(
        description="待求值的数学表达式, 如 '2*x + 3*y' 或 'sqrt(u**2 + 2*a*s)'"
    )
    substitutions: dict[str, float | str] | None = Field(
        default=None,
        description="变量替换映射, 如 {'x': 2, 'y': 'pi/2'}, 字符串值会先经 sympify 解析",
    )


class EvaluateExpressionTool(BaseTool):
    name: str = "evaluate_expression"
    description: str = (
        "求值一个符号数学表达式，可选代入变量后进行数值计算。"
        "支持四则运算、幂运算、三角函数（sin/cos/tan）、对数（log）和指数（exp）。"
        "用于验证物理题答案的数值正确性——必须用此工具实算，不得凭模型自身估算。"
    )
    args_schema: type[BaseModel] = EvaluateParams

    def _run(self, expression: str, substitutions: dict | None = None) -> str:
        return _run_operation("evaluate", expression=expression, substitutions=substitutions or {})

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError


# ---- SolveEquationTool ----

class SolveEquationParams(BaseModel):
    equations: list[str] = Field(
        description="方程列表, 每个方程为等号形式或设为0的表达式, 如 ['x**2 - 4 = 0'] 或 ['x + y - 5']"
    )
    variables: list[str] = Field(
        description="求解的变量列表, 如 ['x'] 或 ['x', 'y']"
    )
    domain: str = Field(
        default="real",
        description="求解域: 'real' 或 'complex'",
    )


class SolveEquationTool(BaseTool):
    name: str = "solve_equation"
    description: str = (
        "求解一个或多个方程。每个方程字符串可以是等号形式（如 'x**2 - 4 = 0'）"
        "或设为0的表达式（如 'x**2 - 4'）。返回解的列表（单方程）或字典列表（方程组）。"
        "用于验证物理题中的方程推导是否正确——必须用此工具实算验证。"
    )
    args_schema: type[BaseModel] = SolveEquationParams

    def _run(self, equations: list[str], variables: list[str], domain: str = "real") -> str:
        return _run_operation("solve", equations=equations, variables=variables, domain=domain)

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError


# ---- CheckEqualityTool ----

class CheckEqualityParams(BaseModel):
    expression_a: str = Field(description="第一个表达式, 如 'sin(x)**2 + cos(x)**2'")
    expression_b: str = Field(description="第二个表达式, 如 '1'")


class CheckEqualityTool(BaseTool):
    name: str = "check_equality"
    description: str = (
        "检查两个数学表达式是否等价（数学恒等关系，非字符串比较）。"
        "使用 SymPy simplify(a - b) == 0 判断。"
        "用于验证两个物理表达式是否一致，如不同推导路径得出的公式是否等价。"
    )
    args_schema: type[BaseModel] = CheckEqualityParams

    def _run(self, expression_a: str, expression_b: str) -> str:
        return _run_operation("equality", expression_a=expression_a, expression_b=expression_b)

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError


# ---- SimplifyExpressionTool ----

class SimplifyParams(BaseModel):
    expression: str = Field(description="待化简/展开的数学表达式, 如 '(x+1)**2' 或 'sin(x)**2 + cos(x)**2'")
    method: str = Field(
        default="simplify",
        description="操作类型: 'simplify'（化简）, 'expand'（展开）, 'factor'（因式分解）, 'trigsimp'（三角化简）",
    )


class SimplifyExpressionTool(BaseTool):
    name: str = "simplify_expression"
    description: str = (
        "对数学表达式进行化简、展开、因式分解或三角化简。"
        "method 可选: simplify（通用化简，默认）, expand（展开）, factor（因式分解）, trigsimp（三角恒等化简）。"
        "用于将物理公式转换形式以验证等价性或简化推导。"
    )
    args_schema: type[BaseModel] = SimplifyParams

    def _run(self, expression: str, method: str = "simplify") -> str:
        return _run_operation("simplify", expression=expression, method=method)

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError


# ---- SolvePhysicsFormulaTool ----

class SolvePhysicsFormulaParams(BaseModel):
    formula: str = Field(
        description="物理公式, 等号形式, 如 'v = u + a*t' 或 'E = 1/2 * m * v**2'"
    )
    solve_for: str = Field(description="要解出的目标变量名, 如 'a' 或 'v'")
    known_values: dict[str, float | str] | None = Field(
        default=None,
        description="已知量的数值, 代入求值, 如 {'v': 20, 'u': 0, 't': 5}. 字符串值先经 sympify 解析",
    )


class SolvePhysicsFormulaTool(BaseTool):
    name: str = "solve_physics_formula"
    description: str = (
        "从物理公式中解出目标变量，可选代入已知数值求结果。"
        "自动重排公式，支持复合公式（如 E = 1/2*m*v^2）。"
        "用于验证物理题中公式推导和数值代入是否正确——必须实算验证。"
    )
    args_schema: type[BaseModel] = SolvePhysicsFormulaParams

    def _run(self, formula: str, solve_for: str, known_values: dict | None = None) -> str:
        return _run_operation(
            "formula", formula=formula, solve_for=solve_for,
            substitutions=known_values or {},
        )

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError


# ---- DimensionalAnalysisTool ----

class DimensionalAnalysisParams(BaseModel):
    expression: str = Field(
        description="带单位的物理表达式, 如 'F = m * a' 或 'kilogram * meter / second**2'"
    )
    operation: str = Field(
        default="check_consistency",
        description="操作: 'check_consistency'（量纲一致性）, 'get_dimensions'（提取量纲）, 'convert'（单位转换）",
    )
    unit_definitions: dict[str, str] | None = Field(
        default=None,
        description="变量到单位的映射, 如 {'F': 'newton', 'm': 'kilogram', 'a': 'meter/second**2'}",
    )
    target_units: str = Field(
        default="",
        description="目标单位表达式, 仅 operation='convert' 时使用, 如 'kilometer / hour'",
    )


class DimensionalAnalysisTool(BaseTool):
    name: str = "dimensional_analysis"
    description: str = (
        "对物理表达式进行量纲分析。支持三种操作："
        "check_consistency — 检查等号两边的量纲是否一致；"
        "get_dimensions — 提取表达式的量纲；"
        "convert — 单位换算（如 5*m/s 转为 km/h）。"
        "用于快速验证物理答案的单位是否正确——量纲不对则答案必然错误。"
    )
    args_schema: type[BaseModel] = DimensionalAnalysisParams

    def _run(
        self, expression: str, operation: str = "check_consistency",
        unit_definitions: dict | None = None, target_units: str = "",
    ) -> str:
        return _run_operation(
            "dimensional", expression=expression, dim_operation=operation,
            unit_definitions=unit_definitions or {}, target_units=target_units,
        )

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError


# ---- ComputeLimitTool ----

class ComputeLimitParams(BaseModel):
    expression: str = Field(description="求极限的表达式, 如 'sin(x)/x'")
    variable: str = Field(description="趋近变量, 如 'x'")
    approach: str = Field(description="趋近值, 如 '0' 或 'oo'（无穷大）")
    direction: str = Field(default="+-", description="方向: '+' 右极限, '-' 左极限, '+-' 双侧极限")


class ComputeLimitTool(BaseTool):
    name: str = "compute_limit"
    description: str = (
        "计算表达式的极限。支持双侧极限和单侧极限。"
        "用于分析物理情景的边界行为——如 t→∞ 时的稳态、x→0 时的近似。"
        "也可验证极值、渐近线等极端情况下的物理合理性。"
    )
    args_schema: type[BaseModel] = ComputeLimitParams

    def _run(self, expression: str, variable: str, approach: str, direction: str = "+-") -> str:
        return _run_operation("limit", expression=expression, variable=variable, approach=approach, direction=direction)

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError


# ---- GeometryConstructTool ----

class GeometryConstructParams(BaseModel):
    expression: str = Field(
        description="几何对象构造表达式, 如 'Line(Point(0,0), Point(h, 2*h))' 或 'Circle(Point(x,y), r)' 或 'Point(x,y).midpoint(Point(a,b))'"
    )


class GeometryConstructTool(BaseTool):
    name: str = "geometry_construct"
    description: str = (
        "构造几何对象：两点定线、过点做垂线、圆心+半径定圆、中点。"
        "使用 SymPy geometry 语法，返回构造出的几何对象的字符串表示。"
        "示例: Line(Point(0,0), Point(1.5*h, h)) 或 Circle(Point(0,0), 2.5*h)"
    )
    args_schema: type[BaseModel] = GeometryConstructParams

    def _run(self, expression: str) -> str:
        return _run_operation("geometry", expression=expression)

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError


# ---- GeometryMeasureTool ----

class GeometryMeasureParams(BaseModel):
    expression: str = Field(
        description="几何测量表达式, 如 'Point(0,0).distance(Point(3*h,4*h))' 或 'l1.angle_between(l2)' 或 'circle.intersection(line)'"
    )


class GeometryMeasureTool(BaseTool):
    name: str = "geometry_measure"
    description: str = (
        "测量几何关系：两点/点线距离、两线夹角、几何交点（线与线、圆与线）、位置判断。"
        "返回数值（距离/夹角）或坐标列表（交点）或布尔值（包含判断）。"
    )
    args_schema: type[BaseModel] = GeometryMeasureParams

    def _run(self, expression: str) -> str:
        return _run_operation("geometry", expression=expression)

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError


# ---- VectorOperationsTool ----

class VectorOperationsParams(BaseModel):
    operation: str = Field(description="向量操作: 'dot'（点积）, 'cross'（叉积）, 'angle'（夹角）, 'projection'（投影）")
    vec_a: list[float] = Field(description="向量A的坐标, 如 [1, 2, 3]")
    vec_b: list[float] = Field(description="向量B的坐标, 如 [4, 5, 6]")


class VectorOperationsTool(BaseTool):
    name: str = "vector_operations"
    description: str = (
        "向量运算：点积、叉积（2D/3D）、向量夹角、向量投影。"
        "用于物理中的功、力矩方向、速度合成、法向/切向分解。"
    )
    args_schema: type[BaseModel] = VectorOperationsParams

    def _run(self, operation: str, vec_a: list, vec_b: list) -> str:
        return _run_operation("vector_ops", vector_operation=operation, vec_a=vec_a, vec_b=vec_b)

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError


# ---- MagneticDeflectionTool ----

class MagneticDeflectionParams(BaseModel):
    entry_point: list[str] = Field(
        description="入射点坐标, 如 ['1.5*h', 'h']（支持符号表达式）"
    )
    velocity_direction: list[float] = Field(
        description="速度方向向量, 如 [3, 4]（无需归一化）"
    )
    impact_point: list[str] = Field(
        description="撞击点坐标, 如 ['0', '-1.5*h']"
    )
    impact_normal: list[float] = Field(
        description="撞击面法向量（指向粒子来的方向）, 如 [0, 1]"
    )


class MagneticDeflectionTool(BaseTool):
    name: str = "magnetic_deflection"
    description: str = (
        "计算带电粒子在匀强磁场中的偏转几何参数。"
        "给定入射点位置、入射速度方向、撞击点坐标和撞击面法向量，"
        "用解析几何解出圆心坐标和偏转半径。"
        "内部使用 SymPy geometry：垂线 → 方程联立 → 自动计算 R。"
        "LLM 只需提供已知量，不需要自己做几何推理。"
    )
    args_schema: type[BaseModel] = MagneticDeflectionParams

    def _run(
        self, entry_point: list, velocity_direction: list,
        impact_point: list, impact_normal: list,
    ) -> str:
        return _run_operation(
            "magnetic_deflection",
            entry_point=entry_point, velocity_direction=velocity_direction,
            impact_point=impact_point, impact_normal=impact_normal,
        )

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError


