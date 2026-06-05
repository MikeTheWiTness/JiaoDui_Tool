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
    "chemistry_balance": Template(
        _SAFE_IMPORTS
        + "\n"
        + "import re as _re\n"
        + "_eq = $equation_str\n"
        + "_sides = _eq.split('->')\n"
        + "_reactants = [s.strip() for s in _sides[0].split('+')]\n"
        + "_products = [s.strip() for s in _sides[1].split('+')]\n"
        + "_all_species = _reactants + _products\n"
        + "_n_react = len(_reactants)\n"
        + "\n"
        + "_elem_pattern = _re.compile(r'([A-Z][a-z]?)(\\d*)')\n"
        + "def _parse_formula(f):\n"
        + "    _counts = {}\n"
        + "    for _m in _elem_pattern.finditer(f):\n"
        + "        _el = _m.group(1)\n"
        + "        _n = int(_m.group(2)) if _m.group(2) else 1\n"
        + "        _counts[_el] = _counts.get(_el, 0) + _n\n"
        + "    return _counts\n"
        + "\n"
        + "_elements = set()\n"
        + "for _s in _all_species:\n"
        + "    _elements.update(_parse_formula(_s).keys())\n"
        + "_elements = sorted(_elements)\n"
        + "\n"
        + "_A = []\n"
        + "for _el in _elements:\n"
        + "    _row = []\n"
        + "    for _i, _s in enumerate(_all_species):\n"
        + "        _cnt = _parse_formula(_s).get(_el, 0)\n"
        + "        if _i >= _n_react:\n"
        + "            _cnt = -_cnt\n"
        + "        _row.append(_cnt)\n"
        + "    _A.append(_row)\n"
        + "\n"
        + "_M = Matrix(_A)\n"
        + "_null = _M.nullspace()\n"
        + "if not _null:\n"
        + "    result = {'error': '无法配平（可能方程式有误）'}\n"
        + "else:\n"
        + "    _vec = _null[0]\n"
        + "    _denoms = [Rational(v).q for v in _vec]\n"
        + "    import math as _math\n"
        + "    _lcm = _denoms[0]\n"
        + "    for _d in _denoms[1:]:\n"
        + "        _lcm = _lcm * _d // _math.gcd(_lcm, _d)\n"
        + "    _coeffs = [abs(int(Rational(v) * _lcm)) for v in _vec]\n"
        + "    _parts = []\n"
        + "    for _i, _s in enumerate(_all_species):\n"
        + "        _co = _coeffs[_i]\n"
        + "        _prefix = str(_co) if _co != 1 else ''\n"
        + "        _parts.append(_prefix + _s)\n"
        + "        if _i == _n_react - 1:\n"
        + "            _parts.append(' -> ')\n"
        + "        elif _i < len(_all_species) - 1:\n"
        + "            _parts.append(' + ')\n"
        + "    result = {'coefficients': _coeffs, "
        + "'reactant_coeffs': _coeffs[:_n_react], "
        + "'product_coeffs': _coeffs[_n_react:], "
        + "'balanced_equation': ''.join(_parts), "
        + "'species': _all_species}\n"
        + _SERIALIZER
    ),
    "stoichiometry": Template(
        _SAFE_IMPORTS
        + "\n"
        + "$molar_masses\n"
        + "_known = $known_substance_str\n"
        + "_target = $target_substance_str\n"
        + "_known_mass = float($known_mass_val)\n"
        + "\n"
        + "_rco = $reactant_coeffs\n"
        + "_pco = $product_coeffs\n"
        + "_react = $reactants_str\n"
        + "_prod = $products_str\n"
        + "\n"
        + "_all = _react + _prod\n"
        + "_coeffs = _rco + _pco\n"
        + "\n"
        + "if _known not in _all or _target not in _all:\n"
        + "    result = {'error': '物质不在方程式中'}\n"
        + "else:\n"
        + "    _ki = _all.index(_known)\n"
        + "    _ti = _all.index(_target)\n"
        + "    _known_mol = _known_mass / _MOLAR[_known]\n"
        + "    _target_mol = _known_mol * (_coeffs[_ti] / _coeffs[_ki])\n"
        + "    _target_mass = _target_mol * _MOLAR[_target]\n"
        + "    result = {\n"
        + "        'known_mass_g': _known_mass,\n"
        + "        'known_mol': float(_known_mol),\n"
        + "        'target_mol': float(_target_mol),\n"
        + "        'target_mass_g': float(_target_mass),\n"
        + "        'mole_ratio': f'{_coeffs[_ti]}:{_coeffs[_ki]}',\n"
        + "    }\n"
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

    # Chemistry params
    equation_str = json_repr(params.get("equation", ""))
    known_substance_str = json_repr(params.get("known_substance", ""))
    target_substance_str = json_repr(params.get("target_substance", ""))
    known_mass_val = json_repr(params.get("known_mass", 0))
    reactant_coeffs = json_repr(params.get("reactant_coeffs", []))
    product_coeffs = json_repr(params.get("product_coeffs", []))
    reactants_str = json_repr(params.get("reactants", []))
    products_str = json_repr(params.get("products", []))

    # Build molar masses dict
    molar_masses = params.get("molar_masses", {}) or {}
    molar_lines = ["_MOLAR = {"]
    for formula, mass in molar_masses.items():
        molar_lines.append(f"    {json_repr(formula)}: {mass},")
    molar_lines.append("}")
    molar_masses_code = "\n".join(molar_lines)

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
        equation_str=equation_str,
        known_substance_str=known_substance_str,
        target_substance_str=target_substance_str,
        known_mass_val=known_mass_val,
        reactant_coeffs=reactant_coeffs,
        product_coeffs=product_coeffs,
        reactants_str=reactants_str,
        products_str=products_str,
        molar_masses=molar_masses_code,
    )


def json_repr(obj) -> str:
    """将 Python 对象转为 JSON 字符串，用于嵌入生成的代码中。"""
    return json.dumps(obj, ensure_ascii=False)
