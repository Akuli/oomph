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
    STRING,
    AutoType,
    FunctionType,
    Type,
    UnionType,
    builtin_generic_types,
    builtin_types,
)


# Custom exception so that we can catch it and not accidentally silence bugs.
# Just spent quite a while wondering what was wrong...
class ConversionError(Exception):
    pass


def _type_members(the_type: Type) -> Set[Type]:
    if isinstance(the_type, UnionType):
        return set(the_type.type_members)
    return {the_type}


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
        self.loop_stack: List[Tuple[ir.GotoLabel, ir.GotoLabel]] = []
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
        if isinstance(raw_type, ast.AutoType):
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
        func = ir.hidden_builtins[name]
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

    # TODO: make sure this logic isn't duplicated elsewhere
    def union_conversion(
        self, var: ir.LocalVariable, target_type: Type
    ) -> ir.LocalVariable:
        conversion_result = self.create_var(target_type)

        if not isinstance(var.type, UnionType):
            if not isinstance(target_type, UnionType):
                # Uncommenting this causes funny corner case and test fail
                # assert var.type == target_type, (var.type, target_type)
                return var
            assert var.type in target_type.type_members
            self.code.append(ir.InstantiateUnion(conversion_result, var))
            self.code.append(ir.IncRef(conversion_result))
            return conversion_result

        bool_var = self.create_var(BOOL)
        end_code: List[ir.Instruction] = []
        done_label = ir.GotoLabel()

        for member in var.type.type_members:
            if member in _type_members(target_type):
                label = ir.GotoLabel()
                self.code.append(ir.UnionMemberCheck(bool_var, var, member))
                self.code.append(ir.Goto(label, bool_var))

                with self.code_to_separate_list() as end_code_stuff:
                    self.code.append(label)
                    get_result = self.create_var(member)  # must be after label
                    self.code.append(ir.GetFromUnion(get_result, var))
                    self.code.append(ir.IncRef(get_result))
                    if isinstance(target_type, UnionType):
                        self.code.append(ir.InstantiateUnion(conversion_result, get_result))
                    else:
                        self.code.append(ir.VarCpy(conversion_result, get_result))
                    self.code.append(ir.IncRef(conversion_result))
                    self.code.append(ir.Goto(done_label, ir.visible_builtins["true"]))

                end_code.extend(end_code_stuff)

        self.code.append(ir.Panic("'as' failed"))  # TODO: better error message?
        self.code.extend(end_code)
        self.code.append(done_label)
        return conversion_result

    def implicit_conversion(
        self, var: ir.LocalVariable, target_type: Type
    ) -> ir.LocalVariable:
        var.type, target_type = self._do_the_autotype_thing(var.type, target_type)

        if var.type is INT and target_type is FLOAT:
            return self.create_special_call("int2float", [var])
        if _type_members(var.type).issubset(_type_members(target_type)):
            return self.union_conversion(var, target_type)

        raise ConversionError(
            f"can't implicitly convert from {var.type.name} to {target_type.name}"
        )

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

            if func is ir.visible_builtins["print"]:
                args = [self.stringify(self.do_expression(arg)) for arg in call.args]
                assert len(args) == 1
            else:
                raw_args = call.args.copy()
                if func is ir.visible_builtins["assert"]:
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

    def _do_binary_op_typed(
        self, lhs: ir.LocalVariable, op: str, rhs: ir.LocalVariable
    ) -> ir.LocalVariable:
        if op in {"in", "not in"}:
            result_var = self.create_var(BOOL)
            self.code.append(ir.CallMethod(rhs, "__contains", [lhs], result_var))
            if op == "not in":
                return self._not(result_var)
            return result_var

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

        if self._substitute_autotypes(lhs.type) != self._substitute_autotypes(rhs.type):
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

    def do_if(
        self,
        cond: ir.LocalVariable,
        then: List[ir.Instruction],
        otherwise: List[ir.Instruction],
    ) -> None:
        then_label = ir.GotoLabel()
        done_label = ir.GotoLabel()
        self.code.append(ir.Goto(then_label, cond))
        self.code.extend(otherwise)
        self.code.append(ir.Goto(done_label, ir.visible_builtins["true"]))
        self.code.append(then_label)
        self.code.extend(then)
        self.code.append(done_label)

    def do_binary_op(self, op_ast: ast.BinaryOperator) -> ir.LocalVariable:
        # Avoid evaluating right side when not needed
        # TODO: mention this in docs
        if op_ast.op in {"and", "or"}:
            lhs_var = self.implicit_conversion(self.do_expression(op_ast.lhs), BOOL)
            result_var = self.create_var(BOOL)
            with self.code_to_separate_list() as rhs_evaluation:
                rhs_var = self.implicit_conversion(self.do_expression(op_ast.rhs), BOOL)

            if op_ast.op == "and":
                self.do_if(
                    lhs_var,
                    rhs_evaluation + [ir.VarCpy(result_var, rhs_var)],
                    [ir.VarCpy(result_var, ir.visible_builtins["false"])],
                )
            else:
                self.do_if(
                    lhs_var,
                    [ir.VarCpy(result_var, ir.visible_builtins["true"])],
                    rhs_evaluation + [ir.VarCpy(result_var, rhs_var)],
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
                assert len({var.type for var in content}) == 1, {
                    var.type for var in content
                }
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
                    assert len(expr.args) == 1
                    obj = self.do_expression(expr.args[0])
                    return self.implicit_conversion(obj, union_type)

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
            if expr.op == "not":
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

        if isinstance(expr, ast.As):
            value = self.do_expression(expr.expr)
            target_type = self.get_type(expr.type)
            assert value.type != target_type, "unnecessary 'as'"
            return self.union_conversion(
                value, target_type
            )

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

        if isinstance(expr, ast.StatementsAndExpression):
            for stmt in expr.statements:
                self.do_statement(stmt)
            return self.do_expression(expr.expression)

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
            assert (new_value_var.type, stmt.attribute) in obj.type.members, (
                f"attribute not found in class {obj.type.name}: "
                f"{new_value_var.type.name} {stmt.attribute}"
            )

            # Copy old value into local var, so that it will be decreffed
            old_value_var = self.create_var(new_value_var.type)
            self.code.append(ir.GetAttribute(obj, old_value_var, stmt.attribute))
            self.code.append(ir.SetAttribute(obj, stmt.attribute, new_value_var))
            self.code.append(ir.IncRef(new_value_var))

        elif isinstance(stmt, ast.Pass):
            pass

        elif isinstance(stmt, ast.Continue):
            continue_label, break_label = self.loop_stack[-1]
            self.code.append(ir.Goto(continue_label, ir.visible_builtins["true"]))

        elif isinstance(stmt, ast.Break):
            continue_label, break_label = self.loop_stack[-1]
            self.code.append(ir.Goto(break_label, ir.visible_builtins["true"]))

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
            self.do_if(condition, body, otherwise)

        elif isinstance(stmt, ast.Loop):
            cond_label = ir.GotoLabel()
            continue_label = ir.GotoLabel()
            break_label = ir.GotoLabel()

            assert isinstance(stmt.loop_header, ast.ForLoopHeader)
            for init in stmt.loop_header.init:
                self.do_statement(init)

            self.code.append(cond_label)
            if stmt.loop_header.cond is None:
                cond_var = self.create_var(BOOL)
                self.code.append(ir.VarCpy(cond_var, ir.visible_builtins["true"]))
            else:
                cond_var = self.do_expression(stmt.loop_header.cond)
            self.code.append(ir.Goto(break_label, self._not(cond_var)))

            self.loop_stack.append((continue_label, break_label))
            self.code.extend(self.do_block(stmt.body))
            popped = self.loop_stack.pop()
            assert popped == (continue_label, break_label)

            self.code.append(continue_label)
            for incr in stmt.loop_header.incr:
                self.do_statement(incr)
            self.code.append(ir.Goto(cond_label, ir.visible_builtins["true"]))
            self.code.append(break_label)

            if len(stmt.loop_header.init) == 1 and isinstance(
                stmt.loop_header.init[0], ast.Let
            ):
                del self.variables[stmt.loop_header.init[0].varname]

        elif isinstance(stmt, ast.Switch):
            union_var = self.do_expression(stmt.union_obj)
            assert isinstance(union_var.type, UnionType)
            types_to_do = set(union_var.type.type_members)

            done_label = ir.GotoLabel()
            member_check = self.create_var(BOOL)

            cases: List[ir.Instruction] = []
            for case in stmt.cases:
                label = ir.GotoLabel()
                cases.append(label)

                if case.type_and_varname is None:
                    assert types_to_do
                    nice_types = types_to_do.copy()
                    types_to_do.clear()
                else:
                    raw_type, varname = case.type_and_varname
                    case_type = self.get_type(raw_type)

                    nice_types = _type_members(case_type)
                    assert nice_types.issubset(types_to_do), case_type
                    types_to_do -= nice_types

                    with self.code_to_separate_list() as case_code:
                        case_var = self.union_conversion(union_var, case_type)

                    cases.extend(case_code)
                    assert varname not in self.variables, varname
                    self.variables[varname] = case_var

                cases.extend(self.do_block(case.body))
                cases.append(ir.Goto(done_label, ir.visible_builtins["true"]))

                if case.type_and_varname is not None:
                    assert self.variables[varname] is case_var
                    del self.variables[varname]

                for typ in nice_types:
                    self.code.append(ir.UnionMemberCheck(member_check, union_var, typ))
                    self.code.append(ir.Goto(label, member_check))

            assert not types_to_do, f"switch does not handle: {types_to_do}"

            # TODO: add panic here (since no union members matched)
            self.code.extend(cases)
            self.code.append(done_label)

        else:
            raise NotImplementedError(stmt)

    def do_block(self, block: List[ast.Statement]) -> List[ir.Instruction]:
        with self.code_to_separate_list() as result:
            for statement in block:
                self.do_statement(statement)
        return result

    def _get_rid_of_auto_in_var(self, var: ir.Variable) -> None:
        if isinstance(var, ir.LocalVariable):
            var.type = self._substitute_autotypes(var.type, must_succeed=True)

    def get_rid_of_auto_everywhere(self) -> None:
        # Method calls can happen before the type is known. Here we assume that
        # the types got figured out.
        for ins in self.code.copy():
            if isinstance(ins, ir.CallMethod):
                self._get_rid_of_auto_in_var(ins.obj)
                functype = self._get_method_functype(ins.obj.type, ins.method_name)
                with self.code_to_separate_list() as front_code:
                    ins.args = self.do_args(
                        ins.args, functype.argtypes, ins.obj, ins.method_name
                    )[1:]
                where = self.code.index(ins)
                self.code[where:where] = front_code

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

        for ins in self.code:
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
                if isinstance(ins, ir.CallFunction):
                    self._get_rid_of_auto_in_var(ins.func)
                # fucking mypy
                assert isinstance(ins, (ir.CallConstructor, ir.CallFunction))
                for arg in ins.args:
                    self._get_rid_of_auto_in_var(arg)
            elif isinstance(ins, ir.VarCpy):
                self._get_rid_of_auto_in_var(ins.dest)
                self._get_rid_of_auto_in_var(ins.source)
            elif isinstance(ins, ir.Goto):
                self._get_rid_of_auto_in_var(ins.cond)
            elif isinstance(ins, ir.Return):
                if ins.value is not None:
                    self._get_rid_of_auto_in_var(ins.value)
            elif isinstance(ins, ir.InstantiateUnion):
                self._get_rid_of_auto_in_var(ins.result)
                self._get_rid_of_auto_in_var(ins.value)
            elif isinstance(ins, ir.GetAttribute):
                self._get_rid_of_auto_in_var(ins.result)
                self._get_rid_of_auto_in_var(ins.obj)
            elif isinstance(ins, ir.SetAttribute):
                self._get_rid_of_auto_in_var(ins.value)
                self._get_rid_of_auto_in_var(ins.obj)
            elif isinstance(ins, (ir.GetFromUnion, ir.UnionMemberCheck)):
                self._get_rid_of_auto_in_var(ins.result)
                self._get_rid_of_auto_in_var(ins.union)
            elif isinstance(ins, (ir.GotoLabel, ir.Panic)):
                pass
            else:
                raise NotImplementedError(ins)


def _create_pointers_equal_method(classtype: Type) -> ir.MethodDef:
    self_var = ir.LocalVariable(classtype)
    other_var = ir.LocalVariable(classtype)
    result_var = ir.LocalVariable(BOOL)
    return ir.MethodDef(
        "equals",
        classtype.methods["equals"],
        [self_var, other_var],
        [ir.PointersEqual(self_var, other_var, result_var), ir.Return(result_var)],
    )


class _FileConverter:
    def __init__(self, path: pathlib.Path, symbols: List[ir.Symbol]) -> None:
        self.path = path
        self.symbols = symbols
        self._types = builtin_types.copy()
        self._generic_types = builtin_generic_types.copy()
        # https://github.com/python/typeshed/issues/5089
        self.variables: Dict[str, ir.Variable] = ir.visible_builtins.copy()  # type: ignore

        # Unions and typedefs are created in pass 1, but content isn't available until pass 2
        self.typedef_laziness: Dict[str, ast.Type] = {}

    def add_var(self, var: ir.Variable, name: str) -> None:
        assert name not in self.variables
        self.variables[name] = var

    def get_named_type(self, name: str) -> Type:
        # Step 2 stuff
        if name in self.typedef_laziness:
            assert name not in self._types
            self._types[name] = self.get_type(self.typedef_laziness.pop(name))
        return self._types[name]

    def get_type(
        self,
        raw_type: ast.Type,
        *,
        recursing_callback: Optional[Callable[[ast.Type], Type]] = None,
    ) -> ir.Type:
        if isinstance(raw_type, ast.AutoType):
            raise RuntimeError("can't use auto type here")
        elif isinstance(raw_type, ast.NamedType):
            return self.get_named_type(raw_type.name)
        elif isinstance(raw_type, ast.UnionType):
            return UnionType(
                [
                    (recursing_callback or self.get_type)(item)
                    for item in raw_type.unioned
                ]
            )
        elif isinstance(raw_type, ast.GenericType):
            return self._generic_types[raw_type.name].get_type(
                (recursing_callback or self.get_type)(raw_type.arg)
            )
        else:
            raise NotImplementedError(raw_type)

    # See docs/syntax.md
    # Step 1: available type names: imports, classes, typedefs, unions
    # Step 2: typedef contents, union contents
    # Step 3: function/method names and signatures, class constructor signatures
    # Step 4: function and method bodies

    def do_step1(self, top_declaration: ast.ToplevelDeclaration) -> None:
        if isinstance(top_declaration, ast.Import):
            for symbol in self.symbols:
                if symbol.path != top_declaration.path:
                    continue

                name = top_declaration.name + "::" + symbol.name
                if isinstance(symbol.value, ir.FileVariable):
                    # Technically step 3, but adding it earlier doesn't matter
                    self.add_var(symbol.value, name)
                else:
                    self._types[name] = symbol.value

        elif isinstance(top_declaration, ast.ClassDef):
            classtype = Type(
                top_declaration.name,
                True,
                self.path,
                create_to_string_method=(
                    "to_string" not in (method.name for method in top_declaration.body)
                ),
            )
            assert top_declaration.name not in self._types
            self._types[top_declaration.name] = classtype

        elif isinstance(top_declaration, ast.TypeDef):
            self.typedef_laziness[top_declaration.name] = top_declaration.type

    def do_step2(self, top_declaration: ast.ToplevelDeclaration) -> None:
        if isinstance(top_declaration, (ast.TypeDef, ast.ClassDef)):
            the_type = self.get_named_type(top_declaration.name)
            self.symbols.append(ir.Symbol(self.path, top_declaration.name, the_type))
            if isinstance(top_declaration, ast.TypeDef) and isinstance(
                the_type, UnionType
            ):
                # use typedef name in error messages
                assert the_type.custom_name is None
                the_type.custom_name = top_declaration.name

    def _func_or_meth_step3(
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

    def do_step3(self, top_declaration: ast.ToplevelDeclaration) -> None:
        if isinstance(top_declaration, ast.FuncOrMethodDef):
            self._func_or_meth_step3(top_declaration, classtype=None)

        elif isinstance(top_declaration, ast.ClassDef):
            classtype = self._types[top_declaration.name]
            classtype.members.extend(
                (self.get_type(typ), nam) for typ, nam in top_declaration.members
            )
            classtype.constructor_argtypes = [typ for typ, nam in classtype.members]

            if "equals" not in (method.name for method in top_declaration.body):
                classtype.methods["equals"] = FunctionType([classtype, classtype], BOOL)

            for method_def in top_declaration.body:
                method_def.args.insert(0, (ast.NamedType(classtype.name), "self"))
                self._func_or_meth_step3(method_def, classtype)

    def _func_or_meth_step4(
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

    def do_step4(
        self,
        top_declaration: ast.ToplevelDeclaration,
    ) -> List[ir.ToplevelDeclaration]:
        if isinstance(top_declaration, ast.FuncOrMethodDef):
            result = self._func_or_meth_step4(top_declaration, classtype=None)
            assert isinstance(result, ir.FuncDef)
            return [result]

        if isinstance(top_declaration, ast.ClassDef):
            classtype = self._types[top_declaration.name]

            typed_method_defs: List[ir.ToplevelDeclaration] = []
            if "equals" not in (method.name for method in top_declaration.body):
                typed_method_defs.append(_create_pointers_equal_method(classtype))

            for method_def in top_declaration.body:
                typed_def = self._func_or_meth_step4(method_def, classtype)
                assert isinstance(typed_def, ir.MethodDef)
                typed_method_defs.append(typed_def)
            return typed_method_defs

        return []


def convert_program(
    program: List[ast.ToplevelDeclaration], path: pathlib.Path, symbols: List[ir.Symbol]
) -> List[ir.ToplevelDeclaration]:
    converter = _FileConverter(path, symbols)

    for top in program:
        converter.do_step1(top)
    for top in program:
        converter.do_step2(top)
    assert not converter.typedef_laziness
    for top in program:
        converter.do_step3(top)

    result = []
    for top in program:
        result.extend(converter.do_step4(top))
    return result
