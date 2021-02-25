from typing import Dict

from compiler.parser import (Call, Expression, ExpressionStatement, FuncDef,
                             GetVar, IntConstant, LetStatement, Statement)
from compiler.types import INT, FunctionType, Type


def _check_expression(var_types: Dict[str, Type], ast: Expression) -> Type:
    if isinstance(ast, IntConstant):
        assert -(2**63) <= ast.value < 2**63
        return INT
    if isinstance(ast, Call):
        functype = _check_expression(var_types, ast.func)
        assert isinstance(functype, FunctionType)
        assert len(ast.args) == len(functype.argtypes)
        for arg, argtype in zip(ast.args, functype.argtypes):
            actual_argtype = _check_expression(var_types, arg)
            assert actual_argtype == argtype, (actual_argtype, argtype)
        return functype.returntype
    if isinstance(ast, GetVar):
        return var_types[ast.varname]
    raise NotImplementedError(ast)


def _check_statement(var_types: Dict[str, Type], ast: Statement) -> None:
    if isinstance(ast, LetStatement):
        assert ast.varname not in var_types
        ast.value_type = _check_expression(var_types, ast.value)
        assert ast.value_type is not None
        var_types[ast.varname] = ast.value_type
    elif isinstance(ast, ExpressionStatement):
        _check_expression(var_types, ast.expression)
    else:
        raise NotImplementedError(ast)


def check_funcdef(var_types: Dict[str, Type], funcdef: FuncDef) -> None:
    var_types[funcdef.name] = funcdef.type
    assert len(funcdef.type.argtypes) == len(funcdef.argnames)
    local_vars = var_types.copy()
    local_vars.update(zip(funcdef.argnames, funcdef.type.argtypes))
    for statement in funcdef.body:
        _check_statement(local_vars, statement)
