from __future__ import annotations

import itertools
import pathlib
from typing import Dict, List, Optional, Tuple, Union

from pyoomph import typed_ast as tast
from pyoomph import untyped_ast as uast
from pyoomph.types import (
    BOOL,
    FLOAT,
    INT,
    OPTIONAL,
    STRING,
    FunctionType,
    Type,
    UnionType,
    builtin_generic_types,
    builtin_types,
)


def _decref_var(var: tast.LocalVariable) -> tast.Statement:
    return tast.DecRef(tast.GetVar(var, incref=False))


class _FunctionOrMethodTyper:
    def __init__(self, file_typer: _FileTyper, variables: Dict[str, tast.Variable]):
        self.file_typer = file_typer
        self.variables = variables
        self.loop_stack: List[Optional[str]] = []  # None means a switch
        self.loop_counter = 0

    def stringify(self, expression: tast.Expression) -> tast.Expression:
        if expression.type == STRING:
            return expression
        return self.create_call(tast.GetMethod(expression, "to_string"), [])

    # Decrefs each argument
    def create_call(self, func: tast.Expression, args: List[tast.Expression]) -> Union[tast.Expression, List[tast.Statement]]:
        if (
            isinstance(func, tast.GetVar)
            and func.var is tast.builtin_variables["print"]
        ):
            args = [self.stringify(arg) for arg in args]
        assert isinstance(func.type, FunctionType)
        assert [arg.type for arg in args] == func.type.argtypes

        # Assumptions:
        #   - function does not need to be decreffed
        #   - getting the function does not have side effects
        assert not func.type.refcounted

        argvars = [tast.LocalVariable('arg', arg.type) for arg in args]
        statements: List[tast.Statement] = [tast.SetLocalVar(var, arg) for var, arg in zip(argvars, args)]
        if func.type.returntype is None:
            statements.append(tast.VoidCall(func, argvars))
            statements.extend(_decref_var(var) for var in argvars)
            return statements

        returnvar = tast.LocalVariable('ret', func.type.returntype)
        statements.append(tast.SetLocalVar(returnvar, tast.ReturningCall(func, argvars)))
        statements.extend(_decref_var(var) for var in argvars)
        return tast.StatementsAndExpression(statements, tast.GetVar(returnvar, decref=False))

    def create_special_call(
        self,
        name: str,
        args: List[tast.Expression],
    ) -> tast.Expression:
        result = self.create_call(tast.special_variables[name], args)
        assert isinstance(result, tast.Expression)
        return result

    def do_call(
        self, ast: uast.Call
    ) -> Union[tast.Expression, tast.Statement]:
        return self.create_call(self.do_expression(ast.func), list(map(self.do_expression, ast.args)))

    def _not(self, ast: tast.Expression) -> tast.Expression:
        return self.create_special_call("bool_not", [ast])

    def _is_null(self, ast: tast.Expression) -> tast.Expression:
        return self.do_call(tast.GetMethod(ast, "is_null"), [])

    def _get_value_of_optional(self, ast: tast.Expression) -> tast.Expression:
        return self.do_call(tast.GetMethod(ast, "get"), [])

    def _do_binary_op_typed(
        self, lhs: tast.Expression, op: str, rhs: tast.Expression
    ) -> tast.Expression:

        if op == "!=":
            return self._not(self._do_binary_op_typed(lhs, "==", rhs))

        # Reduce >=, <=, and < to use >
        if op == "<":
            return self._do_binary_op_typed(rhs, ">", lhs)
        if op == "<=":
            return self._not(self._do_binary_op_typed(lhs, ">", rhs))
        if op == ">=":
            return self._not(self._do_binary_op_typed(lhs, "<", rhs))

        if lhs.type is STRING and op == "+" and rhs.type is STRING:
            # TODO: add something to make a+b+c more efficient than (a+b)+c
            return self.create_special_call("string_concat", [lhs, rhs])
        if (
            lhs.type.generic_origin is not None
            and rhs.type.generic_origin is not None
            and lhs.type.generic_origin.generic is OPTIONAL
            and rhs.type.generic_origin.generic is OPTIONAL
        ):
            lhs_var = tast.LocalVariable("optional_operator_lhs", lhs.type)
            rhs_var = tast.LocalVariable("optional_operator_rhs", rhs.type)
            lhs_with_side_effects = tast.StatementAndExpression(
                tast.CreateLocalVar(lhs_var, lhs),
                tast.StatementAndExpression(
                    tast.CreateLocalVar(rhs_var, rhs),
                    tast.GetVar(lhs_var),
                ),
            )
            return tast.BoolOr(
                tast.BoolAnd(
                    self._is_null(lhs_with_side_effects),
                    self._is_null(tast.GetVar(rhs_var)),
                ),
                tast.BoolAnd(
                    tast.BoolAnd(
                        self._not(self._is_null(tast.GetVar(lhs_var))),
                        self._not(self._is_null(tast.GetVar(rhs_var))),
                    ),
                    self._do_binary_op_typed(
                        self._get_value_of_optional(tast.GetVar(lhs_var)),
                        "==",
                        self._get_value_of_optional(tast.GetVar(rhs_var)),
                    ),
                ),
            )

        if lhs.type is INT and op in {"+", "-", "*", "mod", ">"} and rhs.type is INT:
            return self.create_special_call(
                {
                    "+": "int_add",
                    "-": "int_sub",
                    "*": "int_mul",
                    "mod": "int_mod",
                    ">": "int_gt",
                }[op],
                [lhs, rhs],
            )

        if lhs.type is INT and op == "/" and rhs.type is INT:
            lhs = self.create_special_call("int2float", [lhs])
            rhs = self.create_special_call("int2float", [rhs])
        if lhs.type is INT and rhs.type is FLOAT:
            lhs = self.create_special_call("int2float", [lhs])
        if lhs.type is FLOAT and rhs.type is INT:
            rhs = self.create_special_call("int2float", [rhs])

        if (
            lhs.type is FLOAT
            and op in {"+", "-", "*", "/", "mod", ">"}
            and rhs.type is FLOAT
        ):
            return self.create_special_call(
                {
                    "+": "float_add",
                    "-": "float_sub",
                    "*": "float_mul",
                    "/": "float_div",
                    "mod": "float_mod",
                    ">": "float_gt",
                }[op],
                [lhs, rhs],
            )

        if lhs.type is BOOL and op == "and" and rhs.type is BOOL:
            return tast.BoolAnd(lhs, rhs)
        if lhs.type is BOOL and op == "or" and rhs.type is BOOL:
            return tast.BoolOr(lhs, rhs)
        if lhs.type == rhs.type and op == "==":
            return tast.ReturningCall(tast.GetMethod(lhs, "equals"), [rhs])

        raise NotImplementedError(f"{lhs.type} {op} {rhs.type}")

    def do_binary_op(self, ast: uast.BinaryOperator) -> tast.Expression:
        lhs = self.do_expression(ast.lhs)
        rhs = self.do_expression(ast.rhs)
        return self._do_binary_op_typed(lhs, ast.op, rhs)

    def do_expression_to_string(self, ast: uast.Expression) -> tast.Expression:
        result = self.do_expression(ast)
        if result.type != STRING:
            result = tast.ReturningCall(tast.GetMethod(result, "to_string"), [])
        return result

    def do_expression(self, ast: uast.Expression) -> tast.Expression:
        if isinstance(ast, uast.IntConstant):
            assert -(2 ** 63) <= ast.value < 2 ** 63
            return tast.IntConstant(ast.value)
        if isinstance(ast, uast.FloatConstant):
            return tast.FloatConstant(ast.value)
        if isinstance(ast, uast.StringConstant):
            return tast.StringConstant(ast.value)
        if isinstance(ast, uast.StringFormatJoin):
            assert len(ast.parts) >= 2
            result = self.do_expression_to_string(ast.parts[0])
            for part in ast.parts[1:]:
                # TODO: this results in slow nested code
                result = self.create_special_call(
                    "string_concat", [result, self.do_expression_to_string(part)]
                )
            return result
        if isinstance(ast, uast.Call):
            if isinstance(ast.func, uast.Constructor):
                union_type = self.file_typer.get_type(ast.func.type)
                if isinstance(union_type, UnionType):
                    type_members = self.file_typer.post_process_union(union_type)
                    assert len(ast.args) == 1
                    arg = self.do_expression(ast.args[0])
                    assert arg.type in type_members
                    return tast.InstantiateUnion(union_type, arg)

            call = self.do_call(ast)
            assert not isinstance(call, tast.VoidCall)
            return call
        if isinstance(ast, uast.GetVar):
            return tast.GetVar(self.variables[ast.varname], ast.lineno)
        if isinstance(ast, uast.UnaryOperator):
            obj = self.do_expression(ast.obj)
            if obj.type is BOOL and ast.op == "not":
                return self.create_special_call("bool_not", [obj])
            if obj.type is INT and ast.op == "-":
                return self.create_special_call("int_neg", [obj])
            if obj.type is FLOAT and ast.op == "-":
                return self.create_special_call("float_neg", [obj])
            raise NotImplementedError(f"{ast.op} {obj.type}")
        if isinstance(ast, uast.BinaryOperator):
            return self.do_binary_op(ast)
        if isinstance(ast, uast.Constructor):
            klass = self.file_typer.get_type(ast.type)
            return tast.Constructor(klass.get_constructor_type(), klass)
        if isinstance(ast, uast.GetAttribute):
            obj = self.do_expression(ast.obj)
            try:
                return tast.GetMethod(obj, ast.attribute)
            except KeyError:
                return tast.GetAttribute(obj, ast.attribute)
        elif isinstance(ast, uast.Null):
            return tast.Null(OPTIONAL.get_type(self.file_typer.get_type(ast.type)))
        raise NotImplementedError(ast)

    def do_statement(self, ast: uast.Statement) -> List[tast.Statement]:
        if isinstance(ast, uast.Call):
            result = self.do_call(ast)
            if isinstance(result, tast.SetRef):
                return [tast.DecRef(result.value)]
            return [result]

        if isinstance(ast, uast.Let):
            assert ast.varname not in self.variables, (ast.varname, self.variables)
            value = self.do_expression(ast.value)
            var = tast.LocalVariable(ast.varname, value.type)
            self.variables[var.name] = var
            return [tast.CreateLocalVar(var, value)]

        if isinstance(ast, uast.Assign):
            var2 = self.variables[ast.varname]  # fuck you mypy
            assert isinstance(var2, tast.LocalVariable)
            value = self.do_expression(ast.value)
            assert value.type == var2.type
            return [tast.SetLocalVar(var2, value)]

        if isinstance(ast, uast.Pass):
            return []

        if isinstance(ast, uast.Continue):
            assert self.loop_stack[-1] is not None, "can't continue in switch"
            return [tast.Continue(self.loop_stack[-1])]

        if isinstance(ast, uast.Break):
            assert self.loop_stack[-1] is not None, "can't break in switch"
            return [tast.Break(self.loop_stack[-1])]

        if isinstance(ast, uast.Return):
            if ast.value is None:
                return [tast.Return(None)]
            return [tast.Return(self.do_expression(ast.value))]

        if isinstance(ast, uast.If):
            untyped_condition, untyped_body = ast.ifs_and_elifs[0]
            condition = self.do_expression(untyped_condition)
            assert condition.type is BOOL
            body = self.do_block(untyped_body)

            if len(ast.ifs_and_elifs) >= 2:
                otherwise = self.do_statement(
                    uast.If(ast.ifs_and_elifs[1:], ast.else_block)
                )
            else:
                otherwise = self.do_block(ast.else_block)
            return [tast.If(condition, body, otherwise)]

        if isinstance(ast, uast.Loop):
            init = [] if ast.init is None else self.do_statement(ast.init)
            cond = (
                self.create_special_call("bool_true", [])
                if ast.cond is None
                else self.do_expression(ast.cond)
            )
            incr = [] if ast.incr is None else self.do_statement(ast.incr)

            loop_id = f"loop{self.loop_counter}"
            self.loop_counter += 1

            self.loop_stack.append(loop_id)
            body = self.do_block(ast.body)
            popped = self.loop_stack.pop()
            assert popped == loop_id

            loop = tast.Loop(loop_id, init, cond, incr, body)
            for statement in init:
                if isinstance(statement, tast.CreateLocalVar):
                    var3 = self.variables.pop(statement.var.name)
                    assert var3 is statement.var
            return [loop]

        if isinstance(ast, uast.Switch):
            union_var = self.variables[ast.varname]
            assert isinstance(union_var.type, UnionType)
            types_to_do = self.file_typer.post_process_union(union_var.type).copy()
            self.loop_stack.append(None)

            cases: Dict[tast.LocalVariable, List[tast.Statement]] = {}
            for raw_type, raw_body in ast.cases.items():
                nice_type = self.file_typer.get_type(raw_type)
                types_to_do.remove(nice_type)

                var = tast.LocalVariable(ast.varname, nice_type)
                self.variables[var.name] = var
                cases[var] = self.do_block(raw_body)

            self.variables[ast.varname] = union_var

            assert not types_to_do, types_to_do
            popped = self.loop_stack.pop()
            assert popped is None
            return [tast.Switch(tast.GetVar(union_var), cases)]

        raise NotImplementedError(ast)

    def do_block(self, block: List[uast.Statement]) -> List[tast.Statement]:
        result = []
        for statement in block:
            result.extend(self.do_statement(statement))
        return result


def _create_to_string_method(class_type: tast.Type) -> uast.FuncOrMethodDef:
    strings: List[uast.Expression] = []
    for typ, nam in class_type.members:
        if strings:
            strings.append(uast.StringConstant(", "))
        # FIXME: properly support reference cycling types
        if typ is class_type:
            strings.append(uast.StringConstant(f"<{class_type.name}>"))
        else:
            strings.append(
                uast.Call(
                    uast.GetAttribute(
                        uast.GetAttribute(uast.GetVar("self"), nam), "to_string"
                    ),
                    [],
                )
            )

    strings.insert(0, uast.StringConstant(class_type.name + "("))
    strings.append(uast.StringConstant(")"))

    return uast.FuncOrMethodDef(
        "to_string",
        [],
        uast.Type("Str", None),
        [uast.Return(uast.StringFormatJoin(strings))],
    )


class _FileTyper:
    def __init__(self, path: pathlib.Path, exports: List[tast.Export]) -> None:
        self.path = path
        self.exports = exports
        self._types = builtin_types.copy()
        self._generic_types = builtin_generic_types.copy()
        # https://github.com/python/typeshed/issues/5089
        self.variables: Dict[str, tast.Variable] = tast.builtin_variables.copy()  # type: ignore

        # Union members don't need to exist when union is defined (allows nestedness)
        self.union_laziness: Dict[UnionType, List[uast.Type]] = {}

    def add_var(self, var: tast.Variable, name: Optional[str] = None) -> None:
        if name is None:
            name = var.name
        assert name not in self.variables
        self.variables[name] = var

    def get_type(self, raw_type: uast.Type) -> tast.Type:
        if raw_type.generic is None:
            return self._types[raw_type.name]
        return self._generic_types[raw_type.name].get_type(
            self.get_type(raw_type.generic)
        )

    def _do_func_or_method_def(
        self, funcdef: uast.FuncOrMethodDef, class_name: Optional[str]
    ) -> Union[tast.FuncDef, tast.MethodDef]:
        if class_name is not None:
            funcdef.args.insert(0, (uast.Type(class_name, None), "self"))

        functype = FunctionType(
            [self.get_type(typ) for typ, nam in funcdef.args],
            None if funcdef.returntype is None else self.get_type(funcdef.returntype),
        )

        if class_name is None:
            assert funcdef.name not in self.variables, (
                funcdef.name,
                self.variables.keys(),
            )

            if funcdef.export:
                func_var = tast.ExportVariable(funcdef.name, functype)
                self.exports.append(tast.Export(self.path, funcdef.name, func_var))
                mypy_sucks: Union[tast.ExportVariable, tast.ThisFileVariable] = func_var
            else:
                mypy_sucks = tast.ThisFileVariable(funcdef.name, functype)
            self.add_var(mypy_sucks)

        local_vars = self.variables.copy()
        argvars = []
        for (typename, argname), the_type in zip(funcdef.args, functype.argtypes):
            var = tast.LocalVariable(argname, the_type)
            argvars.append(var)
            assert var.name not in local_vars
            local_vars[var.name] = var

        typer = _FunctionOrMethodTyper(self, local_vars)
        body = typer.do_block(funcdef.body)

        if class_name is None:
            return tast.FuncDef(
                mypy_sucks,
                argvars,
                body,
                typer.reflist,
            )
        else:
            assert not funcdef.export
            return tast.MethodDef(
                funcdef.name,
                functype,
                argvars,
                body,
                typer.reflist,
            )

    def _create_equals_method(self, classtype: Type) -> tast.MethodDef:
        functype = FunctionType([classtype, classtype], BOOL)
        self_var = tast.LocalVariable("self", classtype)
        other_var = tast.LocalVariable("other", classtype)
        return tast.MethodDef(
            "equals",
            functype,
            [self_var, other_var],
            [
                tast.Return(
                    tast.PointersEqual(tast.GetVar(self_var), tast.GetVar(other_var))
                )
            ],
            [],
        )

    def do_toplevel_declaration(
        self,
        top_declaration: uast.ToplevelDeclaration,
    ) -> Optional[tast.ToplevelDeclaration]:
        if isinstance(top_declaration, uast.Import):
            for export in self.exports:
                if export.path != top_declaration.path:
                    continue

                name = top_declaration.name + "::" + export.name
                if isinstance(export.value, tast.ExportVariable):
                    self.add_var(export.value, name)
                else:
                    self._types[name] = export.value
            return None

        if isinstance(top_declaration, uast.FuncOrMethodDef):
            result = self._do_func_or_method_def(top_declaration, class_name=None)
            assert isinstance(result, tast.FuncDef)
            return result

        if isinstance(top_declaration, uast.ClassDef):
            classtype = Type(top_declaration.name, True, self.path)
            assert top_declaration.name not in self._types
            self._types[top_declaration.name] = classtype
            classtype.members.extend(
                (self.get_type(typ), nam) for typ, nam in top_declaration.members
            )
            classtype.constructor_argtypes = [typ for typ, nam in classtype.members]

            if "to_string" not in (method.name for method in top_declaration.body):
                top_declaration.body.insert(0, _create_to_string_method(classtype))

            typed_method_defs = []

            if "equals" not in (method.name for method in top_declaration.body):
                equals_def = self._create_equals_method(classtype)
                typed_method_defs.append(equals_def)
                classtype.methods["equals"] = equals_def.type

            for method_def in top_declaration.body:
                typed_def = self._do_func_or_method_def(
                    method_def, top_declaration.name
                )
                assert isinstance(typed_def, tast.MethodDef)
                classtype.methods[method_def.name] = typed_def.type
                typed_method_defs.append(typed_def)

            if top_declaration.export:
                self.exports.append(
                    tast.Export(self.path, top_declaration.name, classtype)
                )
            return tast.ClassDef(classtype, typed_method_defs, top_declaration.export)

        if isinstance(top_declaration, uast.UnionDef):
            union_type = UnionType(top_declaration.name, self.path)
            self._types[top_declaration.name] = union_type
            self.union_laziness[union_type] = top_declaration.type_members
            if top_declaration.export:
                self.exports.append(
                    tast.Export(self.path, top_declaration.name, union_type)
                )
            return tast.UnionDef(union_type)

        raise NotImplementedError(top_declaration)

    def post_process_union(self, union: UnionType) -> List[Type]:
        if union.type_members is None:
            types = self.union_laziness.pop(union)
            union.set_type_members([self.get_type(t) for t in types])

        assert union.type_members is not None
        return union.type_members


def convert_program(
    program: List[uast.ToplevelDeclaration],
    path: pathlib.Path,
    exports: List[tast.Export],
) -> List[tast.ToplevelDeclaration]:
    typer = _FileTyper(path, exports)
    result = [
        top for top in map(typer.do_toplevel_declaration, program) if top is not None
    ]
    for key in list(typer.union_laziness):
        typer.post_process_union(key)
    return result
