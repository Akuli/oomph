from typing import List

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

    def visit_expression(self, expr: ast.Expression) -> ast.Expression:
        if isinstance(expr, ast.ListComprehension):
            var = self.get_var_name()
            expr = ast.StatementsAndExpression(
                [
                    ast.Let(var, ast.ListLiteral([])),
                    ast.Loop(
                        expr.loop_header,
                        [
                            ast.Call(
                                ast.GetAttribute(ast.GetVar(var), "push"), [expr.value]
                            )
                        ],
                    ),
                ],
                ast.GetVar(var),
            )

        if isinstance(
            expr, (ast.GetVar, ast.IntConstant, ast.StringConstant, ast.FloatConstant)
        ):
            pass
        elif isinstance(expr, ast.StringFormatJoin):
            expr.parts = list(map(self.visit_expression, expr.parts))
        elif isinstance(expr, ast.ListLiteral):
            expr.content = list(map(self.visit_expression, expr.content))
        elif isinstance(expr, ast.StatementsAndExpression):
            expr.statements = self.visit_block(expr.statements)
            expr.expression = self.visit_expression(expr.expression)
        elif isinstance(expr, ast.BinaryOperator):
            expr.lhs = self.visit_expression(expr.lhs)
            expr.rhs = self.visit_expression(expr.rhs)
        elif isinstance(expr, ast.GetAttribute):
            expr.obj = self.visit_expression(expr.obj)
        elif isinstance(expr, ast.Call):
            expr.func = self.visit_expression(expr.func)
            expr.args = list(map(self.visit_expression, expr.args))
        elif isinstance(expr, ast.Constructor):
            pass
        elif isinstance(expr, ast.UnaryOperator):
            expr.obj = self.visit_expression(expr.obj)
        else:
            raise NotImplementedError(expr)

        return expr

    def visit_statement(self, stmt: ast.Statement) -> ast.Statement:
        if isinstance(stmt, ast.Loop) and isinstance(
            stmt.header, ast.ForeachLoopHeader
        ):
            stmt = self.foreach_loop_to_for_loop(stmt)

        if isinstance(stmt, ast.If):
            stmt.ifs_and_elifs = [
                (self.visit_expression(cond), self.visit_block(body))
                for cond, body in stmt.ifs_and_elifs
            ]
            stmt.else_block = self.visit_block(stmt.else_block)
        elif isinstance(stmt, (ast.Let, ast.SetVar)):
            stmt.value = self.visit_expression(stmt.value)
        elif isinstance(stmt, ast.Call):
            stmt.func = self.visit_expression(stmt.func)
            stmt.args = list(map(self.visit_expression, stmt.args))
        elif isinstance(stmt, ast.Return):
            if stmt.value is not None:
                stmt.value = self.visit_expression(stmt.value)
        elif isinstance(stmt, ast.Loop):
            assert isinstance(stmt.header, ast.ForLoopHeader)
            stmt.header.init = self.visit_block(stmt.header.init)
            if stmt.header.cond is not None:
                stmt.header.cond = self.visit_expression(stmt.header.cond)
            stmt.header.incr = self.visit_block(stmt.header.incr)
            stmt.body = self.visit_block(stmt.body)
        elif isinstance(stmt, ast.SetAttribute):
            stmt.obj = self.visit_expression(stmt.obj)
            stmt.value = self.visit_expression(stmt.value)
        elif isinstance(stmt, ast.Pass):
            pass
        else:
            raise NotImplementedError(stmt)

        return stmt

    def visit_block(self, block: List[ast.Statement]) -> List[ast.Statement]:
        return [self.visit_statement(stmt) for stmt in block]


def transform_file(
    decls: List[ast.ToplevelDeclaration],
) -> List[ast.ToplevelDeclaration]:
    result = []
    for decl in decls:
        if isinstance(decl, ast.FuncOrMethodDef):
            decl.body = _AstTransformer().visit_block(decl.body)
        result.append(decl)
    return result
