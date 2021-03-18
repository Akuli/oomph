from __future__ import annotations

import contextlib
import pathlib
from typing import Callable, Dict, Iterator, List, Optional, Set, Tuple, Union

from pyoomph import ast, ir
from pyoomph.types import (
    BOOL,
    FLOAT,
    INT,
    LIST,
    OPTIONAL,
    STRING,
    AutoType,
    FunctionType,
    Type,
    UnionType,
    builtin_generic_types,
    builtin_types,
)


def _get_instructions_recursively(
    code: List[ir.Instruction],
) -> Iterator[Tuple[List[ir.Instruction], ir.Instruction]]:
    for ins in code:
        yield (code, ins)
        if isinstance(ins, ir.If):
            yield from _get_instructions_recursively(ins.then)
            yield from _get_instructions_recursively(ins.otherwise)
        elif isinstance(ins, ir.Loop):
            yield from _get_instructions_recursively(ins.cond_code)
            yield from _get_instructions_recursively(ins.body)
            yield from _get_instructions_recursively(ins.incr)
        elif isinstance(ins, ir.Switch):
            for body in ins.cases.values():
                yield from _get_instructions_recursively(body)


# Custom exception so that we can catch it and not accidentally silence bugs.
# Just spent quite a while wondering what was wrong...
class ConversionError(Exception):
    pass


class _FunctionOrMethodConverter:
    def __init__(
        self,
        file_converter: _FileConverter,
        variables: Dict[str, ir.Variable],
        return_type: Optional[Type],
    ):
        self.file_converter = file_converter
        self.variables = variables
        self.return_type = return_type
        self.loop_stack: List[str] = []
        self.loop_counter = 0
        self.code: List[ir.Instruction] = []
        self.resolved_autotypes: Dict[AutoType, Type] = {}
        self.matching_autotypes: List[Tuple[AutoType, AutoType]] = []

    def _get_matching_autotype_set(self, auto: AutoType) -> Set[AutoType]:
        # TODO: transitivity? if (A,B) and (B,C) in matching_autotypes then A --> {A,B,C}
        matches = {
            typ for pair in self.matching_autotypes for typ in pair if auto in pair
        }
        return matches | {auto}

    def _resolve_autotype(self, auto: AutoType, actual: Type) -> None:
        assert not isinstance(actual, AutoType)
        if auto in self.resolved_autotypes:
            assert self.resolved_autotypes[auto] == actual
        else:
            for matching in self._get_matching_autotype_set(auto):
                self.resolved_autotypes[matching] = actual

    def _substitute_autotypes(self, the_type: Type, must_succeed: bool = False) -> Type:
        if isinstance(the_type, AutoType):
            try:
                return self.resolved_autotypes[the_type]
            except KeyError:
                if must_succeed:
                    raise RuntimeError("can't determine automatic type")
                # Return exactly one of all matching autotypes consistently
                return min(self._get_matching_autotype_set(the_type), key=id)

        if the_type.generic_origin is None:
            return the_type
        return the_type.generic_origin.generic.get_type(
            self._substitute_autotypes(the_type.generic_origin.arg, must_succeed)
        )

    def get_type(self, raw_type: ast.Type) -> ir.Type:
        if raw_type.name == "auto":
            assert raw_type.generic is None, "auto types can't be generic"
            return AutoType()
        return self.file_converter.get_type(raw_type, recursing_callback=self.get_type)

    def create_var(self, the_type: Type) -> ir.LocalVariable:
        # Newly created variables must be decreffed, in case we are in a loop.
        # Also, after decreffing, make sure that another iteration of loop
        # won't decref the same variable again.
        result = ir.LocalVariable(the_type)
        self.code.append(ir.DecRef(result))
        self.code.append(ir.UnSet(result))
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

    def _do_the_autotype_thing(self, type1: Type, type2: Type) -> Tuple[Type, Type]:
        if isinstance(type1, AutoType) and isinstance(type2, AutoType):
            if type1 != type2:
                if type1 in self.resolved_autotypes or type2 in self.resolved_autotypes:
                    return (
                        self.resolved_autotypes.get(type1, type1),
                        self.resolved_autotypes.get(type2, type2),
                    )
                else:
                    self.matching_autotypes.append((type1, type2))
                    return (type1, type1)
        elif isinstance(type1, AutoType):
            try:
                type1 = self.resolved_autotypes[type1]
            except KeyError:
                assert isinstance(type1, AutoType)  # fuck you mypy
                self._resolve_autotype(type1, type2)
                return (type2, type2)
        elif isinstance(type2, AutoType):
            try:
                type2 = self.resolved_autotypes[type2]
            except KeyError:
                assert isinstance(type2, AutoType)  # saatana
                self._resolve_autotype(type2, type1)
                return (type1, type1)
        elif (
            type1.generic_origin is not None
            and type2.generic_origin is not None
            and type1.generic_origin.generic == type2.generic_origin.generic
        ):
            # Handle List[Str] matching List[auto]
            generic = type1.generic_origin.generic
            type1_arg, type2_arg = self._do_the_autotype_thing(
                type1.generic_origin.arg, type2.generic_origin.arg
            )
            return (generic.get_type(type1_arg), generic.get_type(type2_arg))
        return (type1, type2)

    def implicit_conversion(
        self, var: ir.LocalVariable, target_type: Type
    ) -> ir.LocalVariable:
        var.type, target_type = self._do_the_autotype_thing(var.type, target_type)
        if var.type == target_type:
            return var

        if target_type is FLOAT and var.type is INT:
            return self.create_special_call("int2float", [var])

        if not isinstance(target_type, UnionType):
            raise ConversionError(
                f"can't implicitly convert {var.type.name} to {target_type.name}"
            )

        # FIXME: cyclicly nested unions
        result_path: Optional[List[UnionType]] = None
        todo_paths = [[target_type]]
        while todo_paths:
            path = todo_paths.pop()
            assert path[-1].type_members is not None
            for member in path[-1].type_members:
                if member == var.type:
                    if result_path is not None:
                        raise ConversionError("ambiguous implicit conversion")
                    result_path = path
                elif isinstance(member, UnionType):
                    todo_paths.append(path + [member])

        if result_path is None:
            raise ConversionError(
                f"can't implicitly convert from {var.type.name} to {target_type.name}"
            )

        for union in reversed(result_path):
            new_var = self.create_var(union)
            self.code.append(ir.InstantiateUnion(new_var, var))
            self.code.append(ir.IncRef(var))
            var = new_var
        return var

    # Can be called multiple times, that doesn't matter
    def do_args(
        self,
        args: List[ir.LocalVariable],
        target_types: List[Type],
        self_var: Optional[ir.LocalVariable],
        func_name: str,
    ) -> List[ir.LocalVariable]:
        if self_var is not None:
            args = [self_var] + args

        assert len(args) == len(target_types), f"wrong number of args to {func_name}"
        return [
            self.implicit_conversion(var, typ) for var, typ in zip(args, target_types)
        ]

    def _get_method_functype(self, the_type: Type, name: str) -> FunctionType:
        try:
            return the_type.methods[name]
        except KeyError:
            raise RuntimeError(f"{the_type.name} has no method {name}()")

    def _get_attribute_type(self, the_type: Type, attribute: str) -> Type:
        matching_types = [typ for typ, nam in the_type.members if nam == attribute]
        if not matching_types:
            raise RuntimeError(f"{the_type.name} has no attribute {attribute}")
        [result] = matching_types
        return result

    def do_call(
        self, call: ast.Call, must_return_value: bool
    ) -> Optional[ir.LocalVariable]:
        if isinstance(call.func, ast.GetAttribute):
            self_var = self.do_expression(call.func.obj)
            args = [self.do_expression(expr) for expr in call.args]

            self_var.type = self._substitute_autotypes(self_var.type)
            if isinstance(self_var.type, AutoType):
                # Less type information available, do_args will be called later
                if must_return_value:
                    result_var: Optional[ir.LocalVariable] = self.create_var(AutoType())
                else:
                    result_var = None
            else:
                functype = self._get_method_functype(self_var.type, call.func.attribute)
                assert self_var.type == functype.argtypes[0]
                if functype.returntype is None:
                    result_var = None
                else:
                    result_var = self.create_var(functype.returntype)
                args = self.do_args(
                    args, functype.argtypes, self_var, call.func.attribute
                )[1:]
            self.code.append(
                ir.CallMethod(self_var, call.func.attribute, args, result_var)
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
                args = self.do_args(
                    list(map(self.do_expression, raw_args)),
                    func.type.argtypes,
                    None,
                    call.func.varname,
                )
            self.code.append(ir.CallFunction(func, args, result_var))

        elif isinstance(call.func, ast.Constructor):
            the_class = self.get_type(call.func.type)
            assert the_class.constructor_argtypes is not None
            args = self.do_args(
                list(map(self.do_expression, call.args)),
                the_class.constructor_argtypes,
                None,
                f"constructor of {the_class.name}",
            )
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
            new_lhs: Optional[ir.LocalVariable]
            new_rhs: Optional[ir.LocalVariable]

            try:
                new_lhs = self.implicit_conversion(lhs, rhs.type)
            except ConversionError:
                new_lhs = None

            try:
                new_rhs = self.implicit_conversion(rhs, lhs.type)
            except ConversionError:
                new_rhs = None

            if new_lhs is None and new_rhs is not None:
                rhs = new_rhs
            elif new_lhs is not None and new_rhs is None:
                lhs = new_lhs

        if self._substitute_autotypes(
            lhs.type
        ) != self._substitute_autotypes(rhs.type):
            raise RuntimeError(f"{lhs.type.name} {op} {rhs.type.name}")
        the_type = self._substitute_autotypes(lhs.type)

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

        if the_type == FLOAT and op in {"+", "-", "*", "/", "mod", ">"}:
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
            lhs_var = self.implicit_conversion(self.do_expression(op_ast.lhs), BOOL)
            result_var = self.create_var(BOOL)
            with self.code_to_separate_list() as rhs_evaluation:
                rhs_var = self.implicit_conversion(self.do_expression(op_ast.rhs), BOOL)

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
            if content:
                [content_type] = {var.type for var in content}
            else:
                content_type = AutoType()
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
                union_type = self.get_type(expr.func.type)
                if isinstance(union_type, UnionType):
                    var = self.create_var(union_type)
                    assert len(expr.args) == 1
                    obj = self.do_expression(expr.args[0])
                    self.code.append(ir.IncRef(obj))
                    self.code.append(ir.InstantiateUnion(var, obj))
                    return var

            call = self.do_call(expr, True)
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
                return self.create_special_call(
                    "bool_not", [self.implicit_conversion(obj, BOOL)]
                )
            # TODO: auto type support (remember docs)
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
            obj.type = self._substitute_autotypes(obj.type)
            if isinstance(obj.type, AutoType):
                result = self.create_var(AutoType())
            else:
                result = self.create_var(
                    self._get_attribute_type(obj.type, expr.attribute)
                )
            self.code.append(ir.GetAttribute(obj, result, expr.attribute))
            self.code.append(ir.IncRef(result))
            return result

        if isinstance(expr, ast.Null):
            return self.create_var(OPTIONAL.get_type(self.get_type(expr.type)))

        raise NotImplementedError(expr)

    def do_statement(self, stmt: ast.Statement) -> None:
        if isinstance(stmt, ast.Call):
            self.do_call(stmt, False)

        elif isinstance(stmt, ast.Let):
            self.variables[stmt.varname] = self.do_expression(stmt.value)

        elif isinstance(stmt, ast.SetVar):
            var = self.variables[stmt.varname]
            assert isinstance(var, ir.LocalVariable)
            new_value_var = self.do_expression(stmt.value)
            self.code.append(ir.DecRef(var))
            self.code.append(
                ir.VarCpy(var, self.implicit_conversion(new_value_var, var.type))
            )
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
            if self.return_type is None:
                assert stmt.value is None, "unexpected return value"
                self.code.append(ir.Return(None))
            else:
                # TODO: return statements not in every possible branch
                assert stmt.value is not None, "missing return value"
                self.code.append(
                    ir.Return(
                        self.implicit_conversion(
                            self.do_expression(stmt.value), self.return_type
                        )
                    )
                )

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

            loop_id = f"loop{self.loop_counter}"
            self.loop_counter += 1

            self.loop_stack.append(loop_id)
            body = self.do_block(stmt.body)
            popped = self.loop_stack.pop()
            assert popped == loop_id

            incr = [] if stmt.incr is None else self.do_block([stmt.incr])

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
                    nice_type = self.get_type(ugly_type)
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

    def _get_rid_of_auto_in_var(self, var: ir.LocalVariable) -> None:
        var.type = self._substitute_autotypes(var.type, must_succeed=True)

    def get_rid_of_auto_everywhere(self) -> None:
        # Method calls can happen before the type is known. Here we assume that
        # the types got figured out.
        for inslist, ins in list(_get_instructions_recursively(self.code)):
            if isinstance(ins, ir.CallMethod):
                self._get_rid_of_auto_in_var(ins.obj)
                functype = self._get_method_functype(ins.obj.type, ins.method_name)
                with self.code_to_separate_list() as front_code:
                    ins.args = self.do_args(
                        ins.args, functype.argtypes, ins.obj, ins.method_name
                    )[1:]
                where = inslist.index(ins)
                inslist[where:where] = front_code

                if functype.returntype is None:
                    assert ins.result is None
                elif ins.result is not None:
                    if isinstance(ins.result.type, AutoType):
                        self._resolve_autotype(ins.result.type, functype.returntype)
                    else:
                        self._get_rid_of_auto_in_var(ins.result)

                for arg in ins.args:
                    self._get_rid_of_auto_in_var(arg)

            elif isinstance(ins, ir.GetAttribute):
                self._get_rid_of_auto_in_var(ins.obj)
                if isinstance(ins.result.type, AutoType):
                    self._resolve_autotype(
                        ins.result.type,
                        self._get_attribute_type(ins.obj.type, ins.attribute),
                    )
                else:
                    self._get_rid_of_auto_in_var(ins.result)

        for inslist, ins in list(_get_instructions_recursively(self.code)):
            if isinstance(
                ins,
                (
                    ir.DecRef,
                    ir.UnSet,
                    ir.IncRef,
                    ir.IntConstant,
                    ir.StringConstant,
                    ir.FloatConstant,
                ),
            ):
                self._get_rid_of_auto_in_var(ins.var)
            elif isinstance(ins, ir.CallMethod):
                pass  # done separately above
            elif isinstance(ins, (ir.CallConstructor, ir.CallFunction)):
                if ins.result is not None:
                    self._get_rid_of_auto_in_var(ins.result)
                if isinstance(ins, ir.CallFunction) and isinstance(
                    ins.func, ir.LocalVariable
                ):
                    self._get_rid_of_auto_in_var(ins.func)
                for arg in ins.args:
                    self._get_rid_of_auto_in_var(arg)
            elif isinstance(ins, ir.VarCpy):
                self._get_rid_of_auto_in_var(ins.dest)
                if isinstance(ins.source, ir.LocalVariable):
                    self._get_rid_of_auto_in_var(ins.source)
            elif isinstance(ins, ir.If):
                self._get_rid_of_auto_in_var(ins.condition)
            elif isinstance(ins, ir.Loop):
                self._get_rid_of_auto_in_var(ins.cond)
            elif isinstance(ins, ir.Return):
                if ins.value is not None:
                    self._get_rid_of_auto_in_var(ins.value)
            elif isinstance(ins, (ir.InstantiateUnion, ir.IsNull)):
                self._get_rid_of_auto_in_var(ins.result)
                self._get_rid_of_auto_in_var(ins.value)
            elif isinstance(ins, ir.GetAttribute):
                self._get_rid_of_auto_in_var(ins.result)
                self._get_rid_of_auto_in_var(ins.obj)
            elif isinstance(ins, ir.SetAttribute):
                self._get_rid_of_auto_in_var(ins.value)
                self._get_rid_of_auto_in_var(ins.obj)
            elif isinstance(ins, ir.GetFromUnion):
                self._get_rid_of_auto_in_var(ins.result)
                self._get_rid_of_auto_in_var(ins.union)
            elif isinstance(ins, (ir.Continue, ir.Break)):
                pass
            elif isinstance(ins, ir.Switch):
                self._get_rid_of_auto_in_var(ins.union)
                ins.cases = {
                    self._substitute_autotypes(membertype, must_succeed=True): body
                    for membertype, body in ins.cases.items()
                }
            else:
                raise NotImplementedError(ins)


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
    def __init__(self, path: pathlib.Path, symbols: List[ir.Symbol]) -> None:
        self.path = path
        self.symbols = symbols
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

    def get_type(
        self,
        raw_type: ast.Type,
        *,
        recursing_callback: Optional[Callable[[ast.Type], Type]] = None,
    ) -> ir.Type:
        assert raw_type.name != "auto", "can't use auto type here"
        if raw_type.generic is None:
            return self._types[raw_type.name]
        return self._generic_types[raw_type.name].get_type(
            (recursing_callback or self.get_type)(raw_type.generic)
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

            # TODO: use funcdef.export
            func_var = ir.FileVariable(funcdef.name, functype, self.path)
            self.symbols.append(ir.Symbol(self.path, funcdef.name, func_var))
            self.add_var(func_var, funcdef.name)
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

        converter = _FunctionOrMethodConverter(self, local_vars, functype.returntype)
        for statement in funcdef.body:
            converter.do_statement(statement)
        converter.get_rid_of_auto_everywhere()
        body.extend(converter.code)

        if classtype is None:
            assert isinstance(funcvar, ir.FileVariable)
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
            [ir.PointersEqual(self_var, other_var, result_var), ir.Return(result_var)],
        )

    def _create_union_equals_method(self, union_type: UnionType) -> ir.MethodDef:
        assert union_type.type_members
        functype = FunctionType(argtypes=[union_type, union_type], returntype=BOOL)
        self_var = ir.LocalVariable(union_type)
        other_var = ir.LocalVariable(union_type)

        self_switch_cases: Dict[Type, List[ir.Instruction]] = {}
        for self_type in union_type.type_members:
            specific_self_var = ir.LocalVariable(self_type)

            other_switch_cases = {}
            for other_type in union_type.type_members:
                specific_other_var = ir.LocalVariable(other_type)
                result_var = ir.LocalVariable(BOOL)
                other_switch_cases[other_type] = (
                    [
                        ir.GetFromUnion(specific_self_var, self_var),
                        ir.GetFromUnion(specific_other_var, other_var),
                        ir.IncRef(specific_self_var),
                        ir.IncRef(specific_other_var),
                        ir.CallMethod(
                            specific_self_var,
                            "equals",
                            [specific_other_var],
                            result_var,
                        ),
                        ir.Return(result_var),
                    ]
                    if self_type == other_type
                    else [
                        ir.VarCpy(result_var, self.variables["false"]),
                        ir.Return(result_var),
                    ]
                )

            self_switch_cases[self_type] = [ir.Switch(other_var, other_switch_cases)]

        return ir.MethodDef(
            "equals",
            functype,
            [self_var, other_var],
            [ir.Switch(self_var, self_switch_cases)],
        )

    def do_toplevel_declaration_pass1(
        self, top_declaration: ast.ToplevelDeclaration
    ) -> None:
        if isinstance(top_declaration, ast.Import):
            for symbol in self.symbols:
                if symbol.path != top_declaration.path:
                    continue

                name = top_declaration.name + "::" + symbol.name
                if isinstance(symbol.value, ir.FileVariable):
                    self.add_var(symbol.value, name)
                else:
                    self._types[name] = symbol.value

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
    ) -> List[ir.ToplevelDeclaration]:
        if isinstance(top_declaration, ast.Import):
            return []

        if isinstance(top_declaration, ast.FuncOrMethodDef):
            result = self._do_func_or_method_def_pass2(top_declaration, classtype=None)
            assert isinstance(result, ir.FuncDef)
            return [result]

        if isinstance(top_declaration, ast.ClassDef):
            classtype = self._types[top_declaration.name]

            typed_method_defs: List[ir.ToplevelDeclaration] = []
            if "equals" not in (method.name for method in top_declaration.body):
                typed_method_defs.append(self._create_pointers_equal_method(classtype))

            for method_def in top_declaration.body:
                typed_def = self._do_func_or_method_def_pass2(method_def, classtype)
                assert isinstance(typed_def, ir.MethodDef)
                typed_method_defs.append(typed_def)

            # TODO: use top_declaration.export
            self.symbols.append(ir.Symbol(self.path, top_declaration.name, classtype))
            return typed_method_defs

        if isinstance(top_declaration, ast.UnionDef):
            union_type = self._types[top_declaration.name]
            assert isinstance(union_type, UnionType)
            if top_declaration.export:
                self.symbols.append(
                    ir.Symbol(self.path, top_declaration.name, union_type)
                )

            equals = self._create_union_equals_method(union_type)
            return [equals]

        raise NotImplementedError(top_declaration)

    def post_process_union(self, union: UnionType) -> None:
        if union.type_members is None:
            types = self.union_laziness.pop(union)
            union.set_type_members([self.get_type(t) for t in types])


def convert_program(
    program: List[ast.ToplevelDeclaration], path: pathlib.Path, symbols: List[ir.Symbol]
) -> List[ir.ToplevelDeclaration]:
    converter = _FileConverter(path, symbols)
    for top in program:
        converter.do_toplevel_declaration_pass1(top)
    for key in list(converter.union_laziness):
        converter.post_process_union(key)

    result = []
    for top in program:
        result.extend(converter.do_toplevel_declaration_pass2(top))

    return result
