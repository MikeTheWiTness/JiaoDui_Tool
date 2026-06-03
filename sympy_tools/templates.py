import json
from string import Template

_SAFE_IMPORTS = """\
import json
from sympy import sympify, Symbol, symbols, expand, simplify, sqrt, pi, oo, I
from sympy import sin, cos, tan, log, exp, factorial, Rational
from sympy import Matrix, Piecewise, solveset, solve, Eq, limit, diff, integrate
from sympy import factor, trigsimp, together, apart, S
import sympy as _sp
E = Symbol('E')
_LOCALS = dict(locals())
"""

_SERIALIZER = """
def _serialize(obj):
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, (int, float)):
        return float(obj)
    if obj is _sp.S.true:
        return True
    if obj is _sp.S.false:
        return False
    if obj is _sp.S.NaN or obj is None:
        return None
    if hasattr(obj, 'is_number') and obj.is_number and obj is not _sp.oo and obj is not -_sp.oo:
        try:
            return float(obj)
        except (TypeError, ValueError, OverflowError):
            return str(obj)
    if isinstance(obj, _sp.MatrixBase):
        return [[_serialize(obj[i, j]) for j in range(obj.cols)] for i in range(obj.rows)]
    if isinstance(obj, _sp.Piecewise):
        return [{"expr": _serialize(e), "cond": _serialize(c)} for e, c in obj.args]
    if isinstance(obj, (list, tuple)):
        return [_serialize(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): _serialize(v) for k, v in obj.items()}
    return str(obj)

output = _serialize(result)
print(json.dumps(output, ensure_ascii=False))
"""

_TEMPLATES: dict[str, Template] = {
    "evaluate": Template(
        _SAFE_IMPORTS
        + "\nresult = sympify($expression)\n"
        + "$subs_call\n"
        + _SERIALIZER
    ),
    "simplify": Template(
        _SAFE_IMPORTS
        + "\nresult = sympify($expression)\n"
        + "$subs_call\n"
        + "result = $method(result)\n"
        + _SERIALIZER
    ),
    "solve": Template(
        _SAFE_IMPORTS
        + "\neqs = []\n"
        + "for _e in $equations:\n"
        + "    if '=' in _e:\n"
        + "        _parts = _e.rsplit('=', 1)\n"
        + "        eqs.append(Eq(sympify(_parts[0], locals=_LOCALS), sympify(_parts[1], locals=_LOCALS)))\n"
        + "    else:\n"
        + "        eqs.append(sympify(_e, locals=_LOCALS))\n"
        + "vars = symbols($var_names)\n"
        + "result = solve(eqs, vars, dict=True)\n"
        + _SERIALIZER
    ),
    "equality": Template(
        _SAFE_IMPORTS
        + "\na = sympify($expression_a)\n"
        + "b = sympify($expression_b)\n"
        + "diff = simplify(a - b)\n"
        + "result = diff == 0\n"
        + "if not result:\n"
        + "    try:\n"
        + "        result = bool(a.equals(b))\n"
        + "    except Exception:\n"
        + "        pass\n"
        + "if not result:\n"
        + "    sq_diff = simplify(a**2 - b**2)\n"
        + "    result = sq_diff == 0\n"
        + _SERIALIZER
    ),
    "differentiate": Template(
        _SAFE_IMPORTS
        + "\n$substitutions\n"
        + "expr = sympify($expression)\n"
        + "var = Symbol($variable)\n"
        + "result = diff(expr, var, $order)\n"
        + _SERIALIZER
    ),
    "integrate": Template(
        _SAFE_IMPORTS
        + "\n$substitutions\n"
        + "expr = sympify($expression)\n"
        + "var = Symbol($variable)\n"
        + "$limit_code\n"
        + _SERIALIZER
    ),
    "formula": Template(
        _SAFE_IMPORTS
        + "\n_parts = $formula_str.rsplit('=', 1)\n"
        + "_lhs = sympify(_parts[0].strip(), locals=_LOCALS)\n"
        + "_rhs = sympify(_parts[1].strip(), locals=_LOCALS)\n"
        + "_eq = Eq(_lhs, _rhs)\n"
        + "_tgt = Symbol($solve_for)\n"
        + "_sol = solve(_eq, _tgt, dict=True)\n"
        + "result = _sol[0][_tgt] if _sol else None\n"
        + "$subs_call\n"
        + _SERIALIZER
    ),
    "dimensional": Template(
        _SAFE_IMPORTS
        + "from sympy.physics.units import *\n"
        + "from sympy.physics.units import convert_to\n"
        + "from sympy.physics.units.systems.si import dimsys_SI\n"
        + "\n_LOCALS = dict(locals())\n"
        + "$unit_definitions\n"
        + "$operation_code\n"
        + _SERIALIZER
    ),
    "limit": Template(
        _SAFE_IMPORTS
        + "\n_expr = sympify($expression, locals=_LOCALS)\n"
        + "_var = Symbol($variable)\n"
        + "_approach = sympify($approach, locals=_LOCALS)\n"
        + "_dir = $direction\n"
        + "result = limit(_expr, _var, _approach, dir=_dir)\n"
        + _SERIALIZER
    ),
    "geometry": Template(
        _SAFE_IMPORTS
        + "from sympy.geometry import Point, Line, Circle, intersection\n"
        + "\nresult = sympify($expression, locals=_LOCALS)\n"
        + _SERIALIZER
    ),
    "vector_ops": Template(
        _SAFE_IMPORTS
        + "from sympy import Matrix\n"
        + "\n_a = Matrix($vec_a)\n"
        + "_b = Matrix($vec_b)\n"
        + "$op_code\n"
        + _SERIALIZER
    ),
    "magnetic_deflection": Template(
        _SAFE_IMPORTS
        + "from sympy.geometry import Point, Line, Circle, intersection\n"
        + "\n$setup_code\n"
        + "$solve_code\n"
        + _SERIALIZER
    ),
}


def build_code(operation: str, **params) -> str:
    """根据操作类型和参数生成可在子进程中执行的 SymPy Python 代码。"""
    template = _TEMPLATES.get(operation)
    if template is None:
        raise ValueError(f"Unknown operation type: {operation}")

    substitutions = params.get("substitutions", {}) or {}
    if substitutions:
        subs_pairs = []
        for var_name, var_value in substitutions.items():
            if isinstance(var_value, str):
                subs_pairs.append(f'Symbol({var_name!r}): sympify({var_value!r})')
            else:
                subs_pairs.append(f'Symbol({var_name!r}): {var_value!r}')
        subs_call = "result = result.subs({" + ", ".join(subs_pairs) + "})"
    else:
        subs_call = ""

    var_names = " ".join(params.get("variables", ["x"]))

    limit_code = ""
    lower = params.get("lower_limit")
    upper = params.get("upper_limit")
    if lower is not None and upper is not None:
        limit_code = f"result = integrate(expr, (var, sympify({lower!r}), sympify({upper!r})))"
    else:
        limit_code = "result = integrate(expr, var)"

    # Formula-specific params
    formula_str = json_repr(params.get("formula", ""))
    solve_for = json_repr(params.get("solve_for", "x"))

    # Dimensional-analysis params
    operation = params.get("dim_operation", params.get("operation", "check_consistency"))
    target_units = params.get("target_units", "")
    unit_defs = params.get("unit_definitions", {}) or {}
    unit_def_lines = []
    for var_name, unit_str in unit_defs.items():
        unit_def_lines.append(f"{var_name} = sympify({unit_str!r}, locals=_LOCALS)")
    unit_definitions_code = "\n".join(unit_def_lines)

    expression_str = params.get("expression", "")
    if operation == "check_consistency":
        operation_code = (
            f"\n_lr = {expression_str!r}.rsplit('=', 1)\n"
            "_left = sympify(_lr[0].strip(), locals=_LOCALS)\n"
            "_right = sympify(_lr[1].strip(), locals=_LOCALS) if len(_lr) > 1 else None\n"
            "_left_q = [str(q.dimension) for q in _left.atoms(Quantity) if hasattr(q, 'dimension')]\n"
            "_right_q = [str(q.dimension) for q in _right.atoms(Quantity) if hasattr(q, 'dimension')] if _right else []\n"
            "result = {'consistent': sorted(_left_q) == sorted(_right_q), "
            "'left_dimensions': _left_q, "
            "'right_dimensions': _right_q}\n"
        )
    elif operation == "get_dimensions":
        operation_code = (
            f"\n_expr = sympify({expression_str!r}, locals=_LOCALS)\n"
            "_quantities = [a for a in _expr.atoms(Quantity) if hasattr(a, 'dimension')]\n"
            "result = {str(q): str(q.dimension) for q in _quantities}\n"
        )
    elif operation == "convert":
        operation_code = (
            f"\n_expr = sympify({expression_str!r}, locals=_LOCALS)\n"
            f"_target = sympify({target_units!r}, locals=_LOCALS)\n"
            "_converted = convert_to(_expr, _target)\n"
            "result = float((_converted / _target).evalf())\n"
        )
    else:
        operation_code = "\nresult = 'unsupported operation'\n"

    # Vector ops params
    vec_a = params.get("vec_a", [0, 0])
    vec_b = params.get("vec_b", [0, 0])
    op = params.get("vector_operation", params.get("operation", "dot"))
    if op == "dot":
        op_code = "result = float(_a.dot(_b))"
    elif op == "cross":
        op_code = (
            "if len(_a) == 2:\n"
            "    result = float(_a[0]*_b[1] - _a[1]*_b[0])\n"
            "else:\n"
            "    _c = _a.cross(_b)\n"
            "    result = [float(_c[i]) for i in range(len(_c))]"
        )
    elif op == "angle":
        op_code = (
            "from sympy import acos\n"
            "result = float(acos(_a.dot(_b) / (sqrt(_a.dot(_a)) * sqrt(_b.dot(_b)))).evalf())"
        )
    elif op == "projection":
        op_code = (
            "result = [float(x) for x in (_a.dot(_b) / _b.dot(_b)) * _b]"
        )
    else:
        op_code = "result = 'unsupported'"

    # Magnetic deflection params
    entry_point = params.get("entry_point", ["0", "0"])
    velocity_direction = params.get("velocity_direction", [1, 0])
    impact_point = params.get("impact_point", ["0", "0"])
    impact_normal = params.get("impact_normal", [0, 1])

    setup_code = (
        f"_px, _py = sympify({entry_point[0]!r}, locals=_LOCALS), sympify({entry_point[1]!r}, locals=_LOCALS)\n"
        f"_ix, _iy = sympify({impact_point[0]!r}, locals=_LOCALS), sympify({impact_point[1]!r}, locals=_LOCALS)\n"
        f"_P = Point(_px, _py)\n"
        f"_v = Matrix([{velocity_direction[0]}, {velocity_direction[1]}])\n"
        f"_I = Point(_ix, _iy)\n"
        f"_n = Matrix([{impact_normal[0]}, {impact_normal[1]}])\n"
    )
    solve_code = (
        "Cx, Cy = symbols('Cx Cy')\n"
        "_eq1 = Eq((Cx - _P.x)*_v[0] + (Cy - _P.y)*_v[1], 0)\n"
        "_eq2 = Eq((Cx - _I.x)*_n[0] + (Cy - _I.y)*_n[1], 0)\n"
        "_sol = solve([_eq1, _eq2], (Cx, Cy), dict=True)\n"
        "if _sol:\n"
        "    _C = Point(_sol[0][Cx], _sol[0][Cy])\n"
        "    _R = simplify(_C.distance(_P))\n"
        "    result = {'center': [str(_C.x), str(_C.y)], 'radius': str(_R)}\n"
        "else:\n"
        "    result = {'error': 'no_solution'}\n"
    )

    return template.safe_substitute(
        subs_call=subs_call,
        substitutions="",
        expression=json_repr(params.get("expression", "")),
        expression_str=json_repr(params.get("expression", "")),
        expression_a=json_repr(params.get("expression_a", "")),
        expression_b=json_repr(params.get("expression_b", "")),
        equations=json_repr(params.get("equations", [])),
        var_names=json_repr(var_names),
        variables=json_repr(params.get("variables", [])),
        domain=params.get("domain", "S.Reals"),
        variable=json_repr(params.get("variable", "x")),
        order=str(params.get("order", 1)),
        method=params.get("method", "simplify"),
        limit_code=limit_code,
        approach=json_repr(params.get("approach", "0")),
        direction=json_repr(params.get("direction", "+-")),
        formula_str=formula_str,
        solve_for=solve_for,
        unit_definitions=unit_definitions_code,
        operation_code=operation_code,
        target_units=json_repr(target_units),
        vec_a=json_repr(vec_a),
        vec_b=json_repr(vec_b),
        op_code=op_code,
        setup_code=setup_code,
        solve_code=solve_code,
    )


def json_repr(obj) -> str:
    """将 Python 对象转为 JSON 字符串，用于嵌入生成的代码中。"""
    return json.dumps(obj, ensure_ascii=False)
