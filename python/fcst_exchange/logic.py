# SPDX-License-Identifier: MIT OR Apache-2.0
"""Reviewed pure-expression translation; source text is never evaluated."""
import ast
import math
from fcst_contracts import BUNDLE

LANGUAGE = "fcst-expr/1"
PROCEDURE_LANGUAGE = "fcst-pure-return/1"
REGRESSION = "EXCHANGE-LOGIC-001"


def translate(text, language, symbols):
    from .core import reject
    if not isinstance(language,str) or language not in {LANGUAGE, PROCEDURE_LANGUAGE}:
        reject("unreviewed_language")
    if not isinstance(text, str) or len(text.encode("utf-8")) > 4096:
        reject("expression_limit")
    try:
        tree = ast.parse(text, mode="eval")
    except (ValueError, SyntaxError, RecursionError):
        reject("expression_syntax")
    if sum(1 for _ in ast.walk(tree)) > 256:
        reject("expression_limit")
    binary = {ast.Add:"add", ast.Sub:"subtract", ast.Mult:"multiply", ast.Div:"divide"}
    functions = {"abs":1, "sqrt":1, "exp":1, "log":1, "sin":1, "cos":1, "min":2, "max":2}
    def number(node):
        sign = 1
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            sign = -1 if isinstance(node.op, ast.USub) else 1
            node = node.operand
        if not isinstance(node, ast.Constant) or type(node.value) not in (int, float):
            reject("expression_syntax")
        try:
            value = sign * float(node.value)
        except (OverflowError, ValueError):
            reject("expression_range")
        if not math.isfinite(value):
            reject("expression_range")
        return value
    def visit(node, depth=0):
        if depth > 12:
            reject("expression_limit")
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return {"op":"literal", "quantity":{"value":number(node), "unit":"1"}}
        if isinstance(node, ast.Name) and node.id in symbols:
            return {"op":"symbol", "expression_id":symbols[node.id]}
        if isinstance(node, ast.BinOp) and type(node.op) in binary:
            return {"op":binary[type(node.op)], "args":[visit(node.left, depth+1), visit(node.right, depth+1)]}
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return {"op":"negate", "args":[visit(node.operand, depth+1)]}
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            name = node.func.id
            if name == "quantity" and len(node.args) == 2:
                unit = node.args[1]
                if not isinstance(unit, ast.Constant) or type(unit.value) is not str or unit.value not in BUNDLE["units"]:
                    reject("expression_unit")
                return {"op":"literal", "quantity":{"value":number(node.args[0]), "unit":unit.value}}
            if name in functions and len(node.args) == functions[name]:
                return {"op":name, "args":[visit(arg, depth+1) for arg in node.args]}
        reject("untranslated_logic")
    return visit(tree.body)
