# TODO: rename this file
from pyoomph import ast
from typing import List


class _AstTransformer:

    def __init__(self):
        self.varname_counter = 0

    def get_var_name(self):
        # If you use a variable named __var7 in oomph, then wtf.
        self.varname_counter += 1
        return f'__var{self.varname_counter}'

    def foreach_loop_to_for_loop(
        self, loop: ast.Loop
    ) -> List[ast.Statement]:
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
        return [
            ast.Let(index_var, ast.IntConstant(0)),
            ast.Let(list_var, loop.header.list),
            ast.Loop(
                ast.ForLoopHeader(
                None,
                ast.BinaryOperator(
                    ast.GetVar(index_var),
                    "<",
                    ast.Call(
                        ast.GetAttribute(ast.GetVar(list_var), "length"),
                        []
                    ),
                ),
                ast.SetVar(
                    index_var,
                    ast.BinaryOperator(ast.GetVar(index_var), "+", ast.IntConstant(1)),
                )),
                [let] + loop.body,
            ),
        ]

    def transform(self, stmt: ast.Statement) -> List[ast.Statement]:
        if isinstance(stmt, ast.Loop) and isinstance(stmt.header, ast.ForeachLoopHeader):
            return self.transform_list(self.foreach_loop_to_for_loop(stmt))
        return [stmt]

    def transform_list(self, the_list: List[ast.Statement]) -> List[ast.Statement]:
        new_value = []
        for stmt in the_list:
            new_value.extend(self.transform(stmt))
        return new_value


def transform_file(decls: List[ast.ToplevelDeclaration]):
    result = []
    for decl in decls:
        if isinstance(decl, ast.FuncOrMethodDef):
            body = _AstTransformer().transform_list(decl.body)
            result.append(ast.FuncOrMethodDef(decl.name, decl.args, decl.returntype, body, decl.export))
        else:
            result.append(decl)
    return result
