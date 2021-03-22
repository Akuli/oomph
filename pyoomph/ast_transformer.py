import dataclasses
import pathlib
from typing import Any, List

from pyoomph import ast


class _AstTransformer:
    def __init__(self) -> None:
        self.varname_counter = 0

    def get_var_name(self) -> str:
        self.varname_counter += 1
        # Actally using this variable name would be invalid syntax, which is great
        return f"<var{self.varname_counter}>"

    def foreach_loop_to_for_loop(self, loop: ast.Loop) -> ast.Loop:
        assert isinstance(loop.header, ast.ForeachLoopHeader)
        list_var = self.get_var_name()
        index_var = self.get_var_name()

        let: ast.Statement = ast.Let(
            loop.header.varname,
            ast.Call(
                ast.GetAttribute(ast.GetVar(list_var), "get"),
                [ast.GetVar(index_var)],
            ),
        )
        return ast.Loop(
            ast.ForLoopHeader(
                [
                    ast.Let(index_var, ast.IntConstant(0)),
                    ast.Let(list_var, loop.header.list),
                ],
                ast.BinaryOperator(
                    ast.GetVar(index_var),
                    "<",
                    ast.Call(ast.GetAttribute(ast.GetVar(list_var), "length"), []),
                ),
                [
                    ast.SetVar(
                        index_var,
                        ast.BinaryOperator(
                            ast.GetVar(index_var), "+", ast.IntConstant(1)
                        ),
                    )
                ],
            ),
            [let] + loop.body,
        )

    def visit(self, ast_thing: object) -> Any:
        if isinstance(ast_thing, ast.ListComprehension):
            var = self.get_var_name()
            ast_thing = ast.StatementsAndExpression(
                [
                    ast.Let(var, ast.ListLiteral([])),
                    ast.Loop(
                        ast_thing.loop_header,
                        [
                            ast.Call(
                                ast.GetAttribute(ast.GetVar(var), "push"),
                                [ast_thing.value],
                            )
                        ],
                    ),
                ],
                ast.GetVar(var),
            )

        if isinstance(ast_thing, ast.Loop) and isinstance(
            ast_thing.header, ast.ForeachLoopHeader
        ):
            ast_thing = self.foreach_loop_to_for_loop(ast_thing)

        if dataclasses.is_dataclass(ast_thing):
            for name, value in vars(ast_thing).items():
                setattr(ast_thing, name, self.visit(value))
            return ast_thing

        if isinstance(ast_thing, list):
            return [self.visit(item) for item in ast_thing]

        if isinstance(ast_thing, tuple):
            return tuple(self.visit(item) for item in ast_thing)

        if ast_thing is None or isinstance(ast_thing, (str, int, float, pathlib.Path)):
            return ast_thing

        raise NotImplementedError(type(ast_thing))


def transform_file(
    decls: List[ast.ToplevelDeclaration],
) -> List[ast.ToplevelDeclaration]:
    return _AstTransformer().visit(decls)
