from typing import Dict, Optional, List

from compiler.parser import (Call, Expression, FuncDef, GetVar, IntConstant,
                             LetStatement, Statement, DecRef)
from compiler.types import INT, FunctionType, Type


class _BlockChecker:

    def __init__(self, var_types: Dict[str, Type]):
        self.var_types = var_types
        self.decref_list = []

    def _check_call(self, ast: Call) -> Optional[Type]:
        functype = self._check_expression(ast.func)
        assert isinstance(functype, FunctionType)
        assert len(ast.args) == len(functype.argtypes)
        for arg, argtype in zip(ast.args, functype.argtypes):
            actual_argtype = self._check_expression(arg)
            assert actual_argtype == argtype, (actual_argtype, argtype)
        return functype.returntype

    def _check_expression(self, ast: Expression) -> Type:
        if isinstance(ast, IntConstant):
            assert -(2**63) <= ast.value < 2**63
            return INT
        if isinstance(ast, Call):
            returntype = self._check_call(ast)
            assert returntype is not None
            return returntype
        if isinstance(ast, GetVar):
            return self.var_types[ast.varname]
        raise NotImplementedError(ast)

    def _check_statement(self, ast: Statement) -> None:
        if isinstance(ast, LetStatement):
            assert ast.varname not in self.var_types
            ast.value_type = self._check_expression(ast.value)
            assert ast.value_type is not None
            self.var_types[ast.varname] = ast.value_type
        elif isinstance(ast, Call):
            self._check_call(ast)
        else:
            raise NotImplementedError(ast)

    def run(self, block: List[Statement]):
        for statement in block:
            self._check_statement(statement)
        for varname in reversed(self.decref_list):
            block.append(DecRef(varname))


def check_funcdef(var_types: Dict[str, Type], funcdef: FuncDef) -> None:
    var_types[funcdef.name] = funcdef.type
    assert len(funcdef.type.argtypes) == len(funcdef.argnames)
    local_vars = var_types.copy()
    local_vars.update(dict(zip(funcdef.argnames, funcdef.type.argtypes)))
    _BlockChecker(local_vars).run(funcdef.body)
