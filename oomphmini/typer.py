from __future__ import annotations

import pathlib
from typing import Dict, List

from oomphmini import typed_ast as tast
from oomphmini import untyped_ast as uast
from oomphmini.types import FunctionType


class _FunctionOrMethodTyper:
    def __init__(self, file_typer: _FileTyper, variables: Dict[str, tast.Variable]):
        self.variables = variables

    def do_call(self, ast: uast.Call) -> tast.VoidCall:
        func = self.do_expression(ast.func)
        assert isinstance(func.type, FunctionType)
        args = [self.do_expression(arg) for arg in ast.args]
        assert [arg.type for arg in args] == func.type.argtypes, (
            args,
            func.type.argtypes,
        )
        assert func.type.returntype is None
        return tast.VoidCall(func, args)

    def do_expression(self, ast: uast.Expression) -> tast.Expression:
        if isinstance(ast, uast.StringConstant):
            return tast.StringConstant(ast.value)
        if isinstance(ast, uast.GetVar):
            return tast.GetVar(self.variables[ast.varname], ast.lineno)
        raise NotImplementedError(ast)

    def do_statement(self, ast: uast.Statement) -> tast.Statement:
        if isinstance(ast, uast.Call):
            # TODO: decref here if needed
            return self.do_call(ast)
        raise NotImplementedError(ast)

    def do_block(self, block: List[uast.Statement]) -> List[tast.Statement]:
        result = []
        for statement in block:
            result.append(self.do_statement(statement))
        return result


class _FileTyper:
    def __init__(self, path: pathlib.Path, exports: List[tast.Export]) -> None:
        self.path = path
        self.exports = exports
        # https://github.com/python/typeshed/issues/5089
        self.variables: Dict[str, tast.Variable] = tast.builtin_variables.copy()  # type: ignore

    def add_var(self, var: tast.Variable) -> None:
        assert var.name not in self.variables
        self.variables[var.name] = var

    def _do_func_or_method_def(self, funcdef: uast.FuncDef) -> tast.FuncDef:
        assert funcdef.returntype is None
        assert not funcdef.args
        functype = FunctionType([], None)

        assert funcdef.name not in self.variables

        func_var = tast.ExportVariable(funcdef.name, functype)
        self.exports.append(tast.Export(self.path, funcdef.name, func_var))
        self.add_var(func_var)

        local_vars = self.variables.copy()
        assert not funcdef.args
        assert not functype.argtypes

        typer = _FunctionOrMethodTyper(self, local_vars)
        body = typer.do_block(funcdef.body)

        return tast.FuncDef(func_var, [], body, [])

    def do_toplevel_declaration(
        self,
        top_declaration: uast.ToplevelDeclaration,
    ) -> tast.ToplevelDeclaration:
        if isinstance(top_declaration, uast.FuncDef):
            result = self._do_func_or_method_def(top_declaration)
            assert isinstance(result, tast.FuncDef)
            return result
        raise NotImplementedError(top_declaration)


def convert_program(
    program: List[uast.ToplevelDeclaration],
    path: pathlib.Path,
    exports: List[tast.Export],
) -> List[tast.ToplevelDeclaration]:
    typer = _FileTyper(path, exports)
    result = [top for top in map(typer.do_toplevel_declaration, program)]
    return result
