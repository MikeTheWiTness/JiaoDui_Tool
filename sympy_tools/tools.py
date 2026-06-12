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
        "适用于数学/物理/化学/生物题目中的数值验证——必须用此工具实算，不得凭模型自身估算。"
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
        "适用于数学/物理/化学题目中的方程求解与推导验证——必须用此工具实算。"
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
        "适用于数学推导中验证不同路径得出的公式是否一致。"
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
        "适用于数学推导中的公式变形与等价验证。"
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
        "适用于数学分析中的函数边界行为——如 x→∞ 时的渐近线、x→0 时的近似值。"
    )
    args_schema: type[BaseModel] = ComputeLimitParams

    def _run(self, expression: str, variable: str, approach: str, direction: str = "+-") -> str:
        return _run_operation("limit", expression=expression, variable=variable, approach=approach, direction=direction)

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError


# ---- GeometryTool（合并构造+测量） ----

class GeometryParams(BaseModel):
    expression: str = Field(
        description=(
            "几何表达式，支持构造和测量两类操作，可链式调用："
            "构造：Line(Point(x1,y1), Point(x2,y2)) 两点定线、"
            "Line.perpendicular_line(Point) 过点做垂线、"
            "Circle(Point(x,y), r) 圆心+半径定圆、"
            "Point.midpoint(Point) 中点。"
            "测量：.distance() 距离、.angle_between() 夹角、"
            ".intersection() 交点、.encloses_point() 包含判断。"
            "示例: 'Point(0,0).distance(Point(3*h,4*h))' "
            "或 'Circle(Point(0,0), 5).intersection(Line(Point(-10,3), Point(10,3)))'"
        )
    )


class GeometryTool(BaseTool):
    name: str = "geometry"
    description: str = (
        "几何构造与测量工具。支持构造几何对象（点、线、圆、垂线、中点）"
        "以及测量几何关系（距离、夹角、交点、位置判断）。"
        "可链式调用，如先构造再测量：Line(Point(0,0), Point(1,0)).angle_between(Line(Point(0,0), Point(1,1)))。"
        "返回数值（距离/夹角）、坐标列表（交点）或布尔值（包含判断）。"
        "适用于数学几何题的解析构造与验证。"
    )
    args_schema: type[BaseModel] = GeometryParams

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
        "适用于数学向量题以及物理中的功、力矩方向、速度合成、法向/切向分解。"
    )
    args_schema: type[BaseModel] = VectorOperationsParams

    def _run(self, operation: str, vec_a: list, vec_b: list) -> str:
        return _run_operation("vector_ops", vector_operation=operation, vec_a=vec_a, vec_b=vec_b)

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError


# ---- CircleFromTwoPointsTool ----

class CircleFromTwoPointsParams(BaseModel):
    entry_point: list[str] = Field(
        description="第一个点的坐标, 如 ['1.5*h', 'h']（支持符号表达式）。物理题中对应入射点"
    )
    velocity_direction: list[float] = Field(
        description="第一个点处的方向向量（切线方向）, 如 [3, 4]（无需归一化）。物理题中对应速度方向"
    )
    impact_point: list[str] = Field(
        description="第二个点的坐标, 如 ['0', '-1.5*h']。物理题中对应撞击点"
    )
    impact_normal: list[float] = Field(
        description="第二个点处的法向量（指向第一个点所在侧）, 如 [0, 1]。物理题中对应撞击面法向量"
    )


class CircleFromTwoPointsTool(BaseTool):
    name: str = "circle_from_two_points"
    description: str = (
        "根据两点及其方向/法向量求解外接圆的圆心和半径。"
        "给定两个点和各自的几何约束（第一个点的切线方向 + 第二个点的法向量），"
        "通过垂线+方程联立解出唯一的圆心坐标和半径。"
        "适用于：物理磁场偏转题（洛伦兹力提供向心力做圆周运动）、"
        "以及数学中由两点加方向/法向量确定圆的几何问题。"
        "LLM 只需提供已知量，不需要自己做几何推理。"
    )
    args_schema: type[BaseModel] = CircleFromTwoPointsParams

    def _run(
        self, entry_point: list, velocity_direction: list,
        impact_point: list, impact_normal: list,
    ) -> str:
        return _run_operation(
            "circle_from_two_points",
            entry_point=entry_point, velocity_direction=velocity_direction,
            impact_point=impact_point, impact_normal=impact_normal,
        )

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError




# ---- BalanceChemicalEquationTool ----

class BalanceEquationParams(BaseModel):
    equation: str = Field(
        description="待配平的化学方程式, 用 -> 分隔反应物和产物, 如 'Fe + O2 -> Fe2O3' 或 'C2H5OH + O2 -> CO2 + H2O'"
    )


class BalanceChemicalEquationTool(BaseTool):
    name: str = "balance_chemical_equation"
    description: str = (
        "配平化学方程式。输入用 -> 分隔反应物和产物（如 'Fe + O2 -> Fe2O3'），"
        "返回配平后的系数和完整方程式。使用线性代数方法（原子守恒矩阵求解），确保原子数目精确守恒。"
        "用于验证化学题的方程式配平是否正确。"
    )
    args_schema: type[BaseModel] = BalanceEquationParams

    def _run(self, equation: str) -> str:
        return _run_operation("chemistry_balance", equation=equation)

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError


# ---- StoichiometryCalcTool ----

_MOLAR_MASSES: dict[str, float] = {
    "H2O": 18.015, "CO2": 44.01, "CO": 28.01, "CH4": 16.04,
    "C2H5OH": 46.07, "C2H4": 28.05, "C2H2": 26.04, "C6H12O6": 180.16,
    "NaCl": 58.44, "NaOH": 40.00, "Na2CO3": 105.99, "NaHCO3": 84.01,
    "HCl": 36.46, "H2SO4": 98.08, "HNO3": 63.01, "H3PO4": 98.00,
    "NH3": 17.03, "NH4Cl": 53.49, "NH4NO3": 80.04, "NO": 30.01, "NO2": 46.01,
    "CaCO3": 100.09, "CaO": 56.08, "Ca(OH)2": 74.09, "CaCl2": 110.98,
    "Fe": 55.85, "Fe2O3": 159.69, "Fe3O4": 231.53, "FeCl3": 162.20,
    "Al": 26.98, "Al2O3": 101.96, "Al(OH)3": 78.00, "AlCl3": 133.34,
    "Cu": 63.55, "CuO": 79.55, "CuSO4": 159.61, "Cu(OH)2": 97.56,
    "Zn": 65.38, "ZnO": 81.38, "ZnSO4": 161.44,
    "Ag": 107.87, "AgNO3": 169.87, "AgCl": 143.32,
    "KMnO4": 158.03, "K2Cr2O7": 294.18, "KCl": 74.55, "KOH": 56.11,
    "MnO2": 86.94, "SO2": 64.06, "SO3": 80.06,
    "O2": 32.00, "H2": 2.016, "N2": 28.01, "Cl2": 70.90,
    "BaCl2": 208.23, "BaSO4": 233.39, "Ba(OH)2": 171.34,
    "Mg": 24.31, "MgO": 40.30, "Mg(OH)2": 58.32, "MgCl2": 95.21,
}


class StoichiometryParams(BaseModel):
    balanced_equation: str = Field(
        description="已配平的化学方程式, 如 '2H2 + O2 -> 2H2O'"
    )
    known_substance: str = Field(
        description="已知质量的物质化学式, 如 'H2'"
    )
    known_mass: float = Field(
        description="已知物质的质量, 单位克(g), 如 4.0"
    )
    target_substance: str = Field(
        description="待求质量的物质化学式, 如 'H2O'"
    )


class StoichiometryCalcTool(BaseTool):
    name: str = "stoichiometry_calc"
    description: str = (
        "根据已配平的化学方程式和一种物质的质量，计算另一种物质的质量。"
        "自动使用内置摩尔质量数据库（涵盖约50种常见化合物）。"
        "输入：配平方程式 + 已知物质化学式 + 已知质量(g) + 目标物质化学式。"
        "返回：目标物质的物质的量(mol)和质量(g)。"
        "用于验证化学计量计算题的答案。"
    )
    args_schema: type[BaseModel] = StoichiometryParams

    def _run(
        self, balanced_equation: str, known_substance: str,
        known_mass: float, target_substance: str,
    ) -> str:
        import re as _re
        sides = balanced_equation.split("->")
        if len(sides) != 2:
            return json.dumps({"error": "方程式格式错误，需要用 -> 分隔"}, ensure_ascii=False)

        def _parse_side(s):
            coeff_pat = _re.compile(r'^\s*(\d*)\s*([A-Za-z0-9()]+)\s*$')
            result = []
            for p in s.split("+"):
                p = p.strip()
                m = coeff_pat.match(p)
                if m:
                    coeff = int(m.group(1)) if m.group(1) else 1
                    formula = m.group(2)
                    result.append((coeff, formula))
            return result

        reactants = _parse_side(sides[0])
        products = _parse_side(sides[1])
        reactant_coeffs = [c for c, _ in reactants]
        product_coeffs = [c for c, _ in products]
        reactant_formulas = [f for _, f in reactants]
        product_formulas = [f for _, f in products]
        all_formulas = reactant_formulas + product_formulas
        missing = [f for f in all_formulas if f not in _MOLAR_MASSES]
        if missing:
            return json.dumps({
                "error": f"以下物质的摩尔质量不在内置数据库中: {', '.join(missing)}。暂不支持此计算。",
            }, ensure_ascii=False)

        return _run_operation(
            "stoichiometry",
            known_substance=known_substance,
            target_substance=target_substance,
            known_mass=known_mass,
            reactants=reactant_formulas,
            products=product_formulas,
            reactant_coeffs=reactant_coeffs,
            product_coeffs=product_coeffs,
            molar_masses={f: _MOLAR_MASSES[f] for f in all_formulas},
        )

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError
