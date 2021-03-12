from __future__ import annotations

import contextlib
import pathlib
from typing import Dict, Iterator, List, Optional, Union

from pyoomph import ast, ir
from pyoomph.types import (
    BOOL,
    FLOAT,
    INT,
    LIST,
    OPTIONAL,
    STRING,
    FunctionType,
    Type,
    UnionType,
    builtin_generic_types,
    builtin_types,
)


class _FunctionOrMethodConverter:
    def __init__(
        self,
        file_converter: _FileConverter,
        variables: Dict[str, ir.Variable],
    ):
        self.file_converter = file_converter
        self.variables = variables
        self.loop_stack: List[str] = []
        self.loop_counter = 0
        self.code: List[ir.Instruction] = []

    def create_var(self, the_type: Type) -> ir.LocalVariable:
        # Newly created variables must be decreffed, in case we are in a loop.
        # Also, after decreffing, make sure that another iteration of loop
        # won't decref the same variable again.
        result = ir.LocalVariable(the_type)
        self.code.append(ir.DecRef(result))
        self.code.append(ir.SetToNull(result))
        return result

    @contextlib.contextmanager
    def code_to_separate_list(self) -> Iterator[List[ir.Instruction]]:
        result: List[ir.Instruction] = []
        old_code = self.code
        self.code = result
        yield result
        assert self.code is result
        self.code = old_code

    def stringify(self, var: ir.LocalVariable) -> ir.LocalVariable:
        if var.type == STRING:
            return var

        result_var = self.create_var(STRING)
        self.code.append(ir.CallMethod(var, "to_string", [], result_var))
        return result_var

    def create_special_call(
        self, name: str, args: List[ir.LocalVariable]
    ) -> ir.LocalVariable:
        func = ir.special_variables[name]
        assert isinstance(func.type, ir.FunctionType)
        assert func.type.returntype is not None
        result_var = self.create_var(func.type.returntype)
        self.code.append(ir.CallFunction(func, args, result_var))
        return result_var

    def implicit_conversion(
        self, var: ir.LocalVariable, target_type: Type
    ) -> ir.LocalVariable:
        if var.type == target_type:
            return var

        if target_type is FLOAT and var.type is INT:
            return self.create_special_call("int2float", [var])

        if not isinstance(target_type, UnionType):
            raise TypeError("can't implicitly convert {var.type.name} to {target_type.name}")

        # FIXME: cyclicly nested unions
        result_path: Optional[List[UnionType]] = None
        todo_paths = [[target_type]]
        while todo_paths:
            path = todo_paths.pop()
            assert path[-1].type_members is not None
            for member in path[-1].type_members:
                if member == var.type:
                    if result_path is not None:
                        raise TypeError("ambiguous implicit conversion")
                    result_path = path
                elif isinstance(member, UnionType):
                    todo_paths.append(path + [member])

        if result_path is None:
            raise TypeError("can't implicitly convert from {var.type.name} to {target_type.name}")

        for union in reversed(result_path):
            new_var = self.create_var(union)
            self.code.append(ir.InstantiateUnion(new_var, var))
            self.code.append(ir.IncRef(var))
            var = new_var
        return var

    def do_args(
        self, args: List[ast.Expression], target_types: List[Type]
    ) -> List[ir.LocalVariable]:
        assert len(args) == len(target_types)
        return [
            self.implicit_conversion(self.do_expression(expr), typ)
            for expr, typ in zip(args, target_types)
        ]

    def do_call(self, call: ast.Call) -> Optional[ir.LocalVariable]:
        if isinstance(call.func, ast.GetAttribute):
            self_arg = self.do_expression(call.func.obj)
            try:
                functype = self_arg.type.methods[call.func.attribute]
            except KeyError:
                raise RuntimeError(
                    f"{self_arg.type.name} has no method {call.func.attribute}()"
                )
            assert self_arg.type == functype.argtypes[0]
            if functype.returntype is None:
                result_var = None
            else:
                result_var = self.create_var(functype.returntype)
            args = self.do_args(call.args, functype.argtypes[1:])
            self.code.append(
                ir.CallMethod(self_arg, call.func.attribute, args, result_var)
            )
        elif isinstance(call.func, ast.GetVar):
            func = self.variables[call.func.varname]
            assert not isinstance(func, ir.LocalVariable)
            assert isinstance(func.type, ir.FunctionType)
            result_type = func.type.returntype
            if result_type is None:
                result_var = None
            else:
                result_var = self.create_var(result_type)

            if func is ir.builtin_variables["print"]:
                args = [self.stringify(self.do_expression(arg)) for arg in call.args]
                assert len(args) == 1
            else:
                raw_args = call.args.copy()
                if func is ir.builtin_variables["assert"]:
                    assert call.func.lineno is not None
                    # Why relative path:
                    #   - less noise, still enough information
                    #   - tests don't have to include paths like /home/akuli/oomph/...
                    path = self.file_converter.path.relative_to(pathlib.Path.cwd())
                    raw_args.append(ast.StringConstant(str(path)))
                    raw_args.append(ast.IntConstant(call.func.lineno))
                args = self.do_args(raw_args, func.type.argtypes)
            self.code.append(ir.CallFunction(func, args, result_var))
        elif isinstance(call.func, ast.Constructor):
            the_class = self.file_converter.get_type(call.func.type)
            assert the_class.constructor_argtypes is not None
            args = [self.do_expression(arg) for arg in call.args]
            assert [
                arg.type for arg in args
            ] == the_class.constructor_argtypes, the_class.name
            result_var = self.create_var(the_class)
            self.code.append(ir.CallConstructor(result_var, args))
        else:
            raise NotImplementedError

        return result_var

    def _not(self, obj: ir.LocalVariable) -> ir.LocalVariable:
        return self.create_special_call("bool_not", [obj])

    def _get_value_of_optional(self, obj: ir.LocalVariable) -> ir.LocalVariable:
        assert (
            obj.type.generic_origin is not None
            and obj.type.generic_origin.generic is OPTIONAL
        )
        result_var = self.create_var(obj.type.generic_origin.arg)
        self.code.append(ir.CallMethod(obj, "get", [], result_var))
        return result_var

    def _do_binary_op_typed(
        self, lhs: ir.LocalVariable, op: str, rhs: ir.LocalVariable
    ) -> ir.LocalVariable:
        # See docs/implicit-conversions.md
        if lhs.type != rhs.type:
            try:
                new_lhs = self.implicit_conversion(lhs, rhs.type)
            except TypeError:
                new_lhs = None

            try:
                new_rhs = self.implicit_conversion(rhs, lhs.type)
            except TypeError:
                new_rhs = None

            if new_lhs is None and new_rhs is not None:
                rhs = new_rhs
            elif new_lhs is not None and new_rhs is None:
                lhs = new_lhs
            else:
                raise RuntimeError(f"{lhs.type.name} {op} {rhs.type.name}")

        assert lhs.type == rhs.type
        the_type = lhs.type

        if op == "!=":
            return self._not(self._do_binary_op_typed(lhs, "==", rhs))

        # Reduce >=, <=, and < to use >
        if op == "<":
            return self._do_binary_op_typed(rhs, ">", lhs)
        if op == "<=":
            return self._not(self._do_binary_op_typed(lhs, ">", rhs))
        if op == ">=":
            return self._not(self._do_binary_op_typed(lhs, "<", rhs))

        if the_type == STRING and op == "+":
            # TODO: add something to make a+b+c more efficient than (a+b)+c
            return self.create_special_call("string_concat", [lhs, rhs])
        if (
            the_type.generic_origin is not None
        and the_type.generic_origin.generic is OPTIONAL
        ):
            result_var = self.create_var(BOOL)
            with self.code_to_separate_list() as neither_null_code:
                lhs_value = self._get_value_of_optional(lhs)
                rhs_value = self._get_value_of_optional(rhs)
                equal_value = self._do_binary_op_typed(lhs_value, "==", rhs_value)
                self.code.append(ir.VarCpy(result_var, equal_value))

            lhs_null = self.create_var(BOOL)
            rhs_null = self.create_var(BOOL)
            self.code.append(ir.IsNull(lhs, lhs_null))
            self.code.append(ir.IsNull(rhs, rhs_null))

            self.code.append(
                ir.If(
                    lhs_null,
                    [ir.VarCpy(result_var, rhs_null)],
                    [
                        ir.If(
                            rhs_null,
                            [ir.VarCpy(result_var, ir.builtin_variables["false"])],
                            neither_null_code,
                        )
                    ],
                )
            )
            return result_var

        if the_type == INT and op in {"+", "-", "*", "mod", ">"}:
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

        if the_type == INT and op == "/":
            lhs = self.create_special_call("int2float", [lhs])
            rhs = self.create_special_call("int2float", [rhs])
            the_type = FLOAT

        if (
            the_type == FLOAT
            and op in {"+", "-", "*", "/", "mod", ">"}
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

        if op == "==":
            result_var = self.create_var(BOOL)
            self.code.append(ir.CallMethod(lhs, "equals", [rhs], result_var))
            return result_var

        raise TypeError(f"{the_type.name} {op} {the_type.name}")

    def do_binary_op(self, op_ast: ast.BinaryOperator) -> ir.LocalVariable:
        # Avoid evaluating right side when not needed
        # TODO: mention this in docs
        if op_ast.op in {"and", "or"}:
            lhs_var = self.do_expression(op_ast.lhs)
            result_var = self.create_var(BOOL)
            with self.code_to_separate_list() as rhs_evaluation:
                rhs_var = self.do_expression(op_ast.rhs)

            assert lhs_var.type == BOOL
            assert rhs_var.type == BOOL

            if op_ast.op == "and":
                self.code.append(
                    ir.If(
                        lhs_var,
                        rhs_evaluation + [ir.VarCpy(result_var, rhs_var)],
                        [ir.VarCpy(result_var, ir.builtin_variables["false"])],
                    )
                )
            else:
                self.code.append(
                    ir.If(
                        lhs_var,
                        [ir.VarCpy(result_var, ir.builtin_variables["true"])],
                        rhs_evaluation + [ir.VarCpy(result_var, rhs_var)],
                    )
                )
            return result_var

        lhs = self.do_expression(op_ast.lhs)
        rhs = self.do_expression(op_ast.rhs)
        return self._do_binary_op_typed(lhs, op_ast.op, rhs)

    # Always returns new variable
    def do_expression(self, expr: ast.Expression) -> ir.LocalVariable:
        if isinstance(expr, ast.IntConstant):
            assert -(2 ** 63) <= expr.value < 2 ** 63
            var = self.create_var(INT)
            self.code.append(ir.IntConstant(var, expr.value))
            return var

        if isinstance(expr, ast.FloatConstant):
            var = self.create_var(FLOAT)
            self.code.append(ir.FloatConstant(var, expr.value))
            return var

        if isinstance(expr, ast.StringConstant):
            var = self.create_var(STRING)
            self.code.append(ir.StringConstant(var, expr.value))
            return var

        if isinstance(expr, ast.ListLiteral):
            content = [self.do_expression(item) for item in expr.content]
            [content_type] = {var.type for var in content}
            list_var = self.create_var(LIST.get_type(content_type))
            self.code.append(ir.CallConstructor(list_var, []))
            for item_var in content:
                self.code.append(ir.CallMethod(list_var, "push", [item_var], None))
            return list_var

        if isinstance(expr, ast.StringFormatJoin):
            assert len(expr.parts) >= 2
            result = self.stringify(self.do_expression(expr.parts[0]))
            for part in expr.parts[1:]:
                # TODO: this results in slow nested code
                result = self.create_special_call(
                    "string_concat", [result, self.stringify(self.do_expression(part))]
                )
            return result

        if isinstance(expr, ast.Call):
            if isinstance(expr.func, ast.Constructor):
                union_type = self.file_converter.get_type(expr.func.type)
                if isinstance(union_type, UnionType):
                    var = self.create_var(union_type)
                    assert len(expr.args) == 1
                    obj = self.do_expression(expr.args[0])
                    self.code.append(ir.IncRef(obj))
                    self.code.append(ir.InstantiateUnion(var, obj))
                    return var

            call = self.do_call(expr)
            assert call is not None, f"return value of void function {expr.func} used"
            return call

        if isinstance(expr, ast.GetVar):
            # Don't return the same variable, otherwise 'a = a' decrefs too much
            old_var = self.variables[expr.varname]
            new_var = self.create_var(old_var.type)
            self.code.append(ir.VarCpy(new_var, old_var))
            self.code.append(ir.IncRef(new_var))
            return new_var

        if isinstance(expr, ast.UnaryOperator):
            obj = self.do_expression(expr.obj)
            if obj.type is BOOL and expr.op == "not":
                return self.create_special_call("bool_not", [obj])
            if obj.type is INT and expr.op == "-":
                return self.create_special_call("int_neg", [obj])
            if obj.type is FLOAT and expr.op == "-":
                return self.create_special_call("float_neg", [obj])
            raise NotImplementedError(f"{expr.op} {obj.type}")

        if isinstance(expr, ast.BinaryOperator):
            return self.do_binary_op(expr)

        if isinstance(expr, ast.Constructor):
            raise NotImplementedError(f"constructor as object: {expr}")

        if isinstance(expr, ast.GetAttribute):
            obj = self.do_expression(expr.obj)
            matching_types = [
                the_type
                for the_type, name in obj.type.members
                if name == expr.attribute
            ]
            assert matching_types, expr.attribute
            [member_type] = matching_types
            result = self.create_var(member_type)
            self.code.append(ir.GetAttribute(obj, result, expr.attribute))
            self.code.append(ir.IncRef(result))
            return result

        if isinstance(expr, ast.Null):
            # Variables are nulled by default (see create_var)
            return self.create_var(
                OPTIONAL.get_type(self.file_converter.get_type(expr.type))
            )

        raise NotImplementedError(expr)

    def do_statement(self, stmt: ast.Statement) -> None:
        if isinstance(stmt, ast.Call):
            self.do_call(stmt)

        elif isinstance(stmt, ast.Let):
            self.variables[stmt.varname] = self.do_expression(stmt.value)

        elif isinstance(stmt, ast.SetVar):
            var = self.variables[stmt.varname]
            assert isinstance(var, ir.LocalVariable)
            new_value_var = self.do_expression(stmt.value)
            self.code.append(ir.DecRef(var))
            self.code.append(ir.VarCpy(var, new_value_var))
            self.code.append(ir.IncRef(var))

        elif isinstance(stmt, ast.SetAttribute):
            obj = self.do_expression(stmt.obj)
            new_value_var = self.do_expression(stmt.value)
            assert (new_value_var.type, stmt.attribute) in obj.type.members

            # Copy old value into local var, so that it will be decreffed
            old_value_var = self.create_var(new_value_var.type)
            self.code.append(ir.GetAttribute(obj, old_value_var, stmt.attribute))
            self.code.append(ir.SetAttribute(obj, stmt.attribute, new_value_var))
            self.code.append(ir.IncRef(new_value_var))

        elif isinstance(stmt, ast.Pass):
            pass

        elif isinstance(stmt, ast.Continue):
            self.code.append(ir.Continue(self.loop_stack[-1]))

        elif isinstance(stmt, ast.Break):
            self.code.append(ir.Break(self.loop_stack[-1]))

        elif isinstance(stmt, ast.Return):
            # TODO: check return type
            if stmt.value is None:
                self.code.append(ir.Return(None))
            else:
                self.code.append(ir.Return(self.do_expression(stmt.value)))

        elif isinstance(stmt, ast.If):
            untyped_condition, untyped_body = stmt.ifs_and_elifs[0]
            condition = self.do_expression(untyped_condition)
            assert condition.type is BOOL, condition
            body = self.do_block(untyped_body)

            if len(stmt.ifs_and_elifs) >= 2:
                otherwise = self.do_block(
                    [ast.If(stmt.ifs_and_elifs[1:], stmt.else_block)]
                )
            else:
                otherwise = self.do_block(stmt.else_block)
            self.code.append(ir.If(condition, body, otherwise))

        elif isinstance(stmt, ast.Loop):
            if stmt.init is not None:
                self.do_statement(stmt.init)

            if stmt.cond is None:
                cond_var = self.create_var(BOOL)
                mypy_sucks: ir.Instruction = ir.VarCpy(
                    cond_var, ir.builtin_variables["true"]
                )
                cond_code = [mypy_sucks]
            else:
                with self.code_to_separate_list() as cond_code:
                    cond_var = self.do_expression(stmt.cond)

            incr = [] if stmt.incr is None else self.do_block([stmt.incr])

            loop_id = f"loop{self.loop_counter}"
            self.loop_counter += 1

            self.loop_stack.append(loop_id)
            body = self.do_block(stmt.body)
            popped = self.loop_stack.pop()
            assert popped == loop_id

            self.code.append(ir.Loop(loop_id, cond_code, cond_var, incr, body))
            if isinstance(stmt.init, ast.Let):
                del self.variables[stmt.init.varname]

        elif isinstance(stmt, ast.Switch):
            union_var = self.do_expression(stmt.union_obj)
            assert isinstance(union_var.type, UnionType)
            assert union_var.type.type_members is not None
            types_to_do = union_var.type.type_members.copy()

            cases: Dict[ir.Type, List[ir.Instruction]] = {}
            for case in stmt.cases:
                if case.type_and_varname is None:
                    assert types_to_do
                    nice_types = types_to_do.copy()
                    types_to_do.clear()
                else:
                    ugly_type, varname = case.type_and_varname
                    nice_type = self.file_converter.get_type(ugly_type)
                    nice_types = [nice_type]
                    types_to_do.remove(nice_type)
                    case_var = self.create_var(nice_type)
                    assert varname not in self.variables
                    self.variables[varname] = case_var

                body = [
                    ir.GetFromUnion(case_var, union_var),
                    ir.IncRef(case_var),
                ] + self.do_block(case.body)
                for typ in nice_types:
                    cases[typ] = body

                if case.type_and_varname is not None:
                    assert self.variables[varname] is case_var
                    del self.variables[varname]

            assert not types_to_do, types_to_do
            self.code.append(ir.Switch(union_var, cases))

        else:
            raise NotImplementedError(stmt)

    def do_block(self, block: List[ast.Statement]) -> List[ir.Instruction]:
        with self.code_to_separate_list() as result:
            for statement in block:
                self.do_statement(statement)
        return result


def _create_to_string_method(class_type: ir.Type) -> ast.FuncOrMethodDef:
    strings: List[ast.Expression] = []
    for typ, nam in class_type.members:
        if strings:
            strings.append(ast.StringConstant(", "))
        # FIXME: properly support reference cycling types
        if typ is class_type:
            strings.append(ast.StringConstant(f"<{class_type.name}>"))
        else:
            strings.append(
                ast.Call(
                    ast.GetAttribute(
                        ast.GetAttribute(ast.GetVar("self"), nam),
                        "to_string",
                    ),
                    [],
                )
            )

    strings.insert(0, ast.StringConstant(class_type.name + "("))
    strings.append(ast.StringConstant(")"))

    return ast.FuncOrMethodDef(
        "to_string",
        [],
        ast.Type("Str", None),
        [ast.Return(ast.StringFormatJoin(strings))],
    )


class _FileConverter:
    def __init__(self, path: pathlib.Path, exports: List[ir.Export]) -> None:
        self.path = path
        self.exports = exports
        self._types = builtin_types.copy()
        self._generic_types = builtin_generic_types.copy()
        # https://github.com/python/typeshed/issues/5089
        self.variables: Dict[str, ir.Variable] = ir.builtin_variables.copy()  # type: ignore

        # Union members don't need to exist when union is defined (allows nestedness)
        # TODO: is this still necessary?
        self.union_laziness: Dict[UnionType, List[ast.Type]] = {}

    def add_var(self, var: ir.Variable, name: str) -> None:
        assert name not in self.variables
        self.variables[name] = var

    def get_type(self, raw_type: ast.Type) -> ir.Type:
        if raw_type.generic is None:
            return self._types[raw_type.name]
        return self._generic_types[raw_type.name].get_type(
            self.get_type(raw_type.generic)
        )

    def _do_func_or_method_def_pass1(
        self, funcdef: ast.FuncOrMethodDef, classtype: Optional[Type]
    ) -> None:
        functype = FunctionType(
            [self.get_type(typ) for typ, nam in funcdef.args],
            None if funcdef.returntype is None else self.get_type(funcdef.returntype),
        )
        if classtype is None:
            assert funcdef.name not in self.variables, (
                funcdef.name,
                self.variables.keys(),
            )

            if funcdef.export:
                func_var = ir.ExportVariable(funcdef.name, functype)
                self.exports.append(ir.Export(self.path, funcdef.name, func_var))
                mypy_sucks: Union[ir.ExportVariable, ir.ThisFileVariable] = func_var
            else:
                mypy_sucks = ir.ThisFileVariable(funcdef.name, functype)
            self.add_var(mypy_sucks, mypy_sucks.name)
        else:
            assert funcdef.name not in classtype.methods
            classtype.methods[funcdef.name] = functype

    def _do_func_or_method_def_pass2(
        self, funcdef: ast.FuncOrMethodDef, classtype: Optional[Type]
    ) -> Union[ir.FuncDef, ir.MethodDef]:
        if classtype is None:
            funcvar = self.variables[funcdef.name]
            functype = funcvar.type
            assert isinstance(functype, ir.FunctionType)
        else:
            functype = classtype.methods[funcdef.name]

        local_vars = self.variables.copy()
        argvars = []
        body: List[ir.Instruction] = []
        for (typename, argname), the_type in zip(funcdef.args, functype.argtypes):
            argvar = ir.LocalVariable(the_type)
            argvars.append(argvar)

            # Copy arguments to separate local variables to allow assigning to arguments
            copied_var = ir.LocalVariable(the_type)
            body.append(ir.VarCpy(copied_var, argvar))
            body.append(ir.IncRef(copied_var))

            assert argname not in local_vars
            local_vars[argname] = copied_var

        body.extend(_FunctionOrMethodConverter(self, local_vars).do_block(funcdef.body))

        if classtype is None:
            assert isinstance(funcvar, (ir.ThisFileVariable, ir.ExportVariable))
            return ir.FuncDef(funcvar, argvars, body)
        else:
            assert not funcdef.export
            return ir.MethodDef(funcdef.name, functype, argvars, body)

    def _create_pointers_equal_method(self, classtype: Type) -> ir.MethodDef:
        self_var = ir.LocalVariable(classtype)
        other_var = ir.LocalVariable(classtype)
        result_var = ir.LocalVariable(BOOL)
        return ir.MethodDef(
            "equals",
            classtype.methods["equals"],
            [self_var, other_var],
            [
                ir.PointersEqual(self_var, other_var, result_var),
                ir.Return(result_var),
            ],
        )

    def do_toplevel_declaration_pass1(
        self, top_declaration: ast.ToplevelDeclaration
    ) -> None:
        if isinstance(top_declaration, ast.Import):
            for export in self.exports:
                if export.path != top_declaration.path:
                    continue

                name = top_declaration.name + "::" + export.name
                if isinstance(export.value, ir.ExportVariable):
                    self.add_var(export.value, name)
                else:
                    self._types[name] = export.value

        elif isinstance(top_declaration, ast.FuncOrMethodDef):
            self._do_func_or_method_def_pass1(top_declaration, classtype=None)

        elif isinstance(top_declaration, ast.ClassDef):
            classtype = Type(top_declaration.name, True, self.path)
            assert top_declaration.name not in self._types
            self._types[top_declaration.name] = classtype
            classtype.members.extend(
                (self.get_type(typ), nam) for typ, nam in top_declaration.members
            )
            classtype.constructor_argtypes = [typ for typ, nam in classtype.members]

            if "to_string" not in (method.name for method in top_declaration.body):
                top_declaration.body.insert(0, _create_to_string_method(classtype))
            if "equals" not in (method.name for method in top_declaration.body):
                classtype.methods["equals"] = FunctionType([classtype, classtype], BOOL)

            for method_def in top_declaration.body:
                method_def.args.insert(0, (ast.Type(classtype.name, None), "self"))
                self._do_func_or_method_def_pass1(method_def, classtype)

        elif isinstance(top_declaration, ast.UnionDef):
            union_type = UnionType(top_declaration.name, self.path)
            self._types[top_declaration.name] = union_type
            self.union_laziness[union_type] = top_declaration.type_members

        else:
            raise NotImplementedError(top_declaration)

    def do_toplevel_declaration_pass2(
        self,
        top_declaration: ast.ToplevelDeclaration,
    ) -> Optional[ir.ToplevelDeclaration]:
        if isinstance(top_declaration, ast.Import):
            return None

        if isinstance(top_declaration, ast.FuncOrMethodDef):
            result = self._do_func_or_method_def_pass2(top_declaration, classtype=None)
            assert isinstance(result, ir.FuncDef)
            return result

        if isinstance(top_declaration, ast.ClassDef):
            classtype = self._types[top_declaration.name]

            typed_method_defs = []
            if "equals" not in (method.name for method in top_declaration.body):
                equals_def = self._create_pointers_equal_method(classtype)
                typed_method_defs.append(equals_def)

            for method_def in top_declaration.body:
                typed_def = self._do_func_or_method_def_pass2(method_def, classtype)
                assert isinstance(typed_def, ir.MethodDef)
                typed_method_defs.append(typed_def)

            if top_declaration.export:
                self.exports.append(
                    ir.Export(self.path, top_declaration.name, classtype)
                )
            return ir.ClassDef(classtype, typed_method_defs)

        if isinstance(top_declaration, ast.UnionDef):
            union_type = self._types[top_declaration.name]
            assert isinstance(union_type, UnionType)
            if top_declaration.export:
                self.exports.append(
                    ir.Export(self.path, top_declaration.name, union_type)
                )
            return ir.UnionDef(union_type)

        raise NotImplementedError(top_declaration)

    def post_process_union(self, union: UnionType) -> None:
        if union.type_members is None:
            types = self.union_laziness.pop(union)
            union.set_type_members([self.get_type(t) for t in types])


def convert_program(
    program: List[ast.ToplevelDeclaration],
    path: pathlib.Path,
    exports: List[ir.Export],
) -> List[ir.ToplevelDeclaration]:
    converter = _FileConverter(path, exports)
    for top in program:
        converter.do_toplevel_declaration_pass1(top)
    for key in list(converter.union_laziness):
        converter.post_process_union(key)
    result = [
        top
        for top in map(converter.do_toplevel_declaration_pass2, program)
        if top is not None
    ]
    return result
