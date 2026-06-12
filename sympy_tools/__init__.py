from sympy_tools.safety import check_dangerous
from sympy_tools.sandbox import execute_code
from sympy_tools.templates import build_code
from sympy_tools.tools import (
    EvaluateExpressionTool,
    SolveEquationTool,
    CheckEqualityTool,
    SimplifyExpressionTool,
    SolvePhysicsFormulaTool,
    DimensionalAnalysisTool,
    ComputeLimitTool,
    GeometryTool,
    VectorOperationsTool,
    CircleFromTwoPointsTool,
    BalanceChemicalEquationTool,
    StoichiometryCalcTool,
)

ALL_TOOLS = [
    EvaluateExpressionTool(),
    SolveEquationTool(),
    CheckEqualityTool(),
    SimplifyExpressionTool(),
    SolvePhysicsFormulaTool(),
    DimensionalAnalysisTool(),
    ComputeLimitTool(),
    GeometryTool(),
    VectorOperationsTool(),
    CircleFromTwoPointsTool(),
    BalanceChemicalEquationTool(),
    StoichiometryCalcTool(),
]


def get_tools_for_langgraph():
    return ALL_TOOLS
