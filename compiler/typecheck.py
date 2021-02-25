from typing import Dict, List, Optional, Set

from compiler.parser import (Call, ClassDef, DecRef, Expression, FuncDef,
                             GetVar, IntConstant, LetStatement, Statement,
                             ToplevelStatement)
from compiler.types import FunctionType, NamedType, Type


class _BlockChecker:

    def __init__(self, variables: Dict[str, Type]):
        self.variables = variables
        self.decref_list: List[str] = []

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
            return NamedType('int')
        if isinstance(ast, Call):
            returntype = self._check_call(ast)
            assert returntype is not None
            return returntype
        if isinstance(ast, GetVar):
            return self.variables[ast.varname]
        raise NotImplementedError(ast)

    def _check_statement(self, ast: Statement) -> None:
        if isinstance(ast, LetStatement):
            assert ast.varname not in self.variables
            ast.value_type = self._check_expression(ast.value)
            assert ast.value_type is not None
            self.variables[ast.varname] = ast.value_type
        elif isinstance(ast, Call):
            self._check_call(ast)
        else:
            raise NotImplementedError(ast)

    def run(self, block: List[Statement]) -> None:
        for statement in block:
            self._check_statement(statement)
        for varname in reversed(self.decref_list):
            block.append(DecRef(varname))


def _check_toplevel_statement(variables: Dict[str, Type], type_names: Set[str], top_statement: ToplevelStatement) -> None:
    if isinstance(top_statement, FuncDef):
        variables[top_statement.name] = top_statement.type
        assert len(top_statement.type.argtypes) == len(top_statement.argnames)
        local_vars = variables.copy()
        local_vars.update(dict(zip(top_statement.argnames, top_statement.type.argtypes)))
        _BlockChecker(local_vars).run(top_statement.body)
    elif isinstance(top_statement, ClassDef):
        type_names.add(top_statement.name)
    else:
        raise NotImplementedError(top_statement)


def check_program(program: List[ToplevelStatement]) -> None:
    type_names = {'int'}
    variables: Dict[str, Type] = {
        'add': FunctionType([NamedType('int'), NamedType('int')], NamedType('int')),
        'print_int': FunctionType([NamedType('int')], None),
    }
    for toplevel_statement in program:
        _check_toplevel_statement(variables, type_names, toplevel_statement)
