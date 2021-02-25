from typing import Dict, List, Optional, Set

from compiler import typed_ast as tast
from compiler import untyped_ast as uast
from compiler.types import INT, FunctionType, Type


class _BlockTyper:

    def __init__(self, variables: Dict[str, Type]):
        self.variables = variables
        self.decref_list: List[str] = []

    def do_call(self, ast: uast.Call) -> tast.Call:
        raise NotImplementedError
#        functype = self._check_expression(ast.func)
#        assert isinstance(functype, FunctionType)
#        assert len(ast.args) == len(functype.argtypes)
#        for arg, argtype in zip(ast.args, functype.argtypes):
#            actual_argtype = self._check_expression(arg)
#            assert actual_argtype == argtype, (actual_argtype, argtype)
#        return functype.returntype

    def do_expression(self, ast: uast.Expression) -> tast.Expression:
#        if isinstance(ast, IntConstant):
#            assert -(2**63) <= ast.value < 2**63
#            return INT
#        if isinstance(ast, Call):
#            returntype = self._check_call(ast)
#            assert returntype is not None
#            return returntype
#        if isinstance(ast, GetVar):
#            return self.variables[ast.varname]
        raise NotImplementedError(ast)

    def do_statement(self, ast: uast.Statement) -> tast.Statement:
#        if isinstance(ast, LetStatement):
#            assert ast.varname not in self.variables
#            ast.value_type = self._check_expression(ast.value)
#            assert ast.value_type is not None
#            self.variables[ast.varname] = ast.value_type
#        elif isinstance(ast, Call):
#            self._check_call(ast)
#        else:
            raise NotImplementedError(ast)

    def run(self, block: List[uast.Statement]) -> List[tast.Statement]:
        typed_statements = [self.do_statement(s) for s in block]
        decrefs: List[tast.Statement] = [tast.DecRef(varname) for varname in self.decref_list]
        return typed_statements + decrefs[::-1]


def _check_toplevel_statement(variables: Dict[str, Type], types: Dict[str, Type], top_statement: uast.ToplevelStatement) -> tast.ToplevelStatement:
#    if isinstance(top_statement, FuncDef):
#        variables[top_statement.name] = top_statement.type
#        assert len(top_statement.type.argtypes) == len(top_statement.argnames)
#        local_vars = variables.copy()
#        local_vars.update(dict(zip(top_statement.argnames, top_statement.type.argtypes)))
#        _BlockChecker(local_vars).run(top_statement.body)
#    elif isinstance(top_statement, ClassDef):
#        types.add(top_statement.name)
#    else:
        raise NotImplementedError(top_statement)


def convert_program(program: List[uast.ToplevelStatement]) -> List[tast.ToplevelStatement]:
    types: Dict[str, Type] = {'int': INT}
    variables: Dict[str, Type] = {
        'add': FunctionType([INT, INT], INT),
        'print_int': FunctionType([INT], None),
    }
    return [_check_toplevel_statement(variables, types, toplevel_statement)
            for toplevel_statement in program]
