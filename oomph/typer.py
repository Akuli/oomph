from __future__ import annotations

import itertools
from typing import Dict, List, Optional, Tuple, Union

from oomph import typed_ast as tast
from oomph import untyped_ast as uast
from oomph.types import (
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
    builtin_variables,
)

_special_funcs = {
    "bool_eq": FunctionType([BOOL, BOOL], BOOL),
    "bool_false": FunctionType([], BOOL),
    "bool_not": FunctionType([BOOL], BOOL),
    "bool_true": FunctionType([], BOOL),
    "float_add": FunctionType([FLOAT, FLOAT], FLOAT),
    "float_div": FunctionType([FLOAT, FLOAT], FLOAT),
    "float_eq": FunctionType([FLOAT, FLOAT], BOOL),
    "float_gt": FunctionType([FLOAT, FLOAT], BOOL),
    "float_mod": FunctionType([FLOAT, FLOAT], FLOAT),
    "float_mul": FunctionType([FLOAT, FLOAT], FLOAT),
    "float_neg": FunctionType([FLOAT], FLOAT),
    "float_sub": FunctionType([FLOAT, FLOAT], FLOAT),
    "int2float": FunctionType([INT], FLOAT),
    "int_add": FunctionType([INT, INT], INT),
    "int_eq": FunctionType([INT, INT], BOOL),
    "int_gt": FunctionType([INT, INT], BOOL),
    "int_mod": FunctionType([INT, INT], INT),
    "int_mul": FunctionType([INT, INT], INT),
    "int_neg": FunctionType([INT], INT),
    "int_sub": FunctionType([INT, INT], INT),
    "string_concat": FunctionType([STRING, STRING], STRING),
    "string_eq": FunctionType([STRING, STRING], BOOL),
}


class _FunctionOrMethodTyper:
    def __init__(self, file_typer: _FileTyper, variables: Dict[str, Type]):
        self.file_typer = file_typer
        self.variables = variables
        self.reflist: List[Tuple[str, Type]] = []
        self.loop_stack: List[Optional[str]] = []  # None means a switch
        self.loop_counter = 0
        self.ref_names = (f"ref{n}" for n in itertools.count())

    def create_returning_call(
        self, func: tast.Expression, args: List[tast.Expression]
    ) -> Union[tast.SetRef, tast.ReturningCall]:
        result = tast.ReturningCall(func, args)
        if result.type.refcounted:
            refname = next(self.ref_names)
            self.reflist.append((refname, result.type))
            return tast.SetRef(result.type, refname, result)
        return result

    def create_special_call(
        self,
        name: str,
        args: List[tast.Expression],
    ) -> Union[tast.SetRef, tast.ReturningCall]:
        functype = _special_funcs[name]
        actual_argtypes = [arg.type for arg in args]
        assert actual_argtypes == functype.argtypes, (
            name,
            actual_argtypes,
            functype.argtypes,
        )
        return self.create_returning_call(
            tast.GetVar(_special_funcs[name], name, is_special=True), args
        )

    def do_call(
        self, ast: uast.Call
    ) -> Union[tast.VoidCall, tast.ReturningCall, tast.SetRef]:
        func = self.do_expression(ast.func)
        assert isinstance(func.type, FunctionType)

        # Stringify automagically when printing
        if isinstance(func, tast.GetVar) and func.varname == "print":
            args = [self.do_expression_to_string(arg) for arg in ast.args]
        else:
            args = [self.do_expression(arg) for arg in ast.args]

        assert [arg.type for arg in args] == func.type.argtypes

        if func.type.returntype is None:
            return tast.VoidCall(func, args)
        return self.create_returning_call(func, args)

    def do_binary_op(self, ast: uast.BinaryOperator) -> tast.Expression:
        if ast.op == "!=":
            return self.create_special_call(
                "bool_not",
                [self.do_binary_op(uast.BinaryOperator(ast.lhs, "==", ast.rhs))],
            )

        # Reduce >=, <=, and < to use >
        if ast.op == "<":
            ast = uast.BinaryOperator(ast.rhs, ">", ast.lhs)
        if ast.op == "<=":
            ast = uast.BinaryOperator(ast.rhs, ">=", ast.lhs)
        if ast.op == ">=":
            return self.create_special_call(
                "bool_not",
                [self.do_binary_op(uast.BinaryOperator(ast.lhs, "<", ast.rhs))],
            )

        lhs = self.do_expression(ast.lhs)
        rhs = self.do_expression(ast.rhs)
        if lhs.type is STRING and ast.op == "+" and rhs.type is STRING:
            # TODO: add something to make a+b+c more efficient than (a+b)+c
            return self.create_special_call("string_concat", [lhs, rhs])
        if lhs.type is STRING and ast.op == "==" and rhs.type is STRING:
            return self.create_special_call("string_eq", [lhs, rhs])

        if (
            lhs.type is INT
            and ast.op in {"+", "-", "*", "mod", ">"}
            and rhs.type is INT
        ):
            return self.create_special_call(
                {
                    "+": "int_add",
                    "-": "int_sub",
                    "*": "int_mul",
                    "mod": "int_mod",
                    ">": "int_gt",
                }[ast.op],
                [lhs, rhs],
            )

        if lhs.type is INT and ast.op == "/" and rhs.type is INT:
            lhs = self.create_special_call("int2float", [lhs])
            rhs = self.create_special_call("int2float", [rhs])
        if lhs.type is INT and rhs.type is FLOAT:
            lhs = self.create_special_call("int2float", [lhs])
        if lhs.type is FLOAT and rhs.type is INT:
            rhs = self.create_special_call("int2float", [rhs])

        if (
            lhs.type is FLOAT
            and ast.op in {"+", "-", "*", "/", "mod", ">"}
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
                }[ast.op],
                [lhs, rhs],
            )

        if lhs.type is BOOL and ast.op == "and" and rhs.type is BOOL:
            return tast.BoolAnd(lhs, rhs)
        if lhs.type is BOOL and ast.op == "or" and rhs.type is BOOL:
            return tast.BoolOr(lhs, rhs)
        if lhs.type is BOOL and ast.op == "==" and rhs.type is BOOL:
            return self.create_special_call("bool_eq", [lhs, rhs])
        if lhs.type is INT and ast.op == "==" and rhs.type is INT:
            return self.create_special_call("int_eq", [lhs, rhs])
        if lhs.type is FLOAT and ast.op == "==" and rhs.type is FLOAT:
            # Float equality sucks, but maybe it can be useful for something
            return self.create_special_call("float_eq", [lhs, rhs])
            return tast.NumberEqual(lhs, rhs)

        raise NotImplementedError(f"{lhs.type} {ast.op} {rhs.type}")

    def do_expression_to_string(self, ast: uast.Expression) -> tast.Expression:
        result = self.do_expression(ast)
        if result.type != STRING:
            result = self.create_returning_call(tast.GetMethod(result, "to_string"), [])
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
            if ast.varname == "true":
                return self.create_special_call("bool_true", [])
            if ast.varname == "false":
                return self.create_special_call("bool_false", [])
            return tast.GetVar(self.variables[ast.varname], ast.varname, ast.lineno)
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
            self.variables[ast.varname] = value.type
            return [tast.CreateLocalVar(ast.varname, value)]

        if isinstance(ast, uast.Assign):
            # TODO: this assumes local variable without assert
            vartype = self.variables[ast.varname]
            value = self.do_expression(ast.value)
            assert value.type is vartype
            return [tast.SetLocalVar(ast.varname, value)]

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
            if isinstance(ast.init, uast.Let):
                del self.variables[ast.init.varname]
                return [loop, tast.DeleteLocalVar(ast.init.varname)]
            return [loop]

        if isinstance(ast, uast.ForEach):
            # Convert to for loop (less code elsewhere)
            list_var = f"__foreach_list_{self.loop_counter}"
            index_var = f"__foreach_index_{self.loop_counter}"
            self.loop_counter += 1

            get_from_list_to_var: uast.Statement = uast.Let(
                ast.varname,
                uast.Call(
                    uast.GetAttribute(uast.GetVar(list_var), "get"),
                    [uast.GetVar(index_var)],
                ),
            )
            the_loop = uast.Loop(
                None,
                uast.BinaryOperator(
                    uast.GetVar(index_var),
                    "<",
                    uast.Call(
                        uast.GetAttribute(uast.GetVar(list_var), "length"),
                        [],
                    ),
                ),
                uast.Assign(
                    index_var,
                    uast.BinaryOperator(
                        uast.GetVar(index_var), "+", uast.IntConstant(1)
                    ),
                ),
                [get_from_list_to_var] + ast.body,
            )
            return (
                self.do_block(
                    [
                        uast.Let(index_var, uast.IntConstant(0)),
                        uast.Let(list_var, ast.list),
                        the_loop,
                    ]
                )
                + [tast.DeleteLocalVar(index_var), tast.DeleteLocalVar(list_var)]
            )

        if isinstance(ast, uast.Switch):
            utype = self.variables[ast.varname]
            assert isinstance(utype, UnionType)
            types_to_do = self.file_typer.post_process_union(utype).copy()
            self.loop_stack.append(None)

            cases: Dict[Type, List[tast.Statement]] = {}
            for raw_type, raw_body in ast.cases.items():
                nice_type = self.file_typer.get_type(raw_type)
                types_to_do.remove(nice_type)

                self.variables[ast.varname] = nice_type
                cases[nice_type] = self.do_block(raw_body)

            self.variables[ast.varname] = utype

            assert not types_to_do, types_to_do
            popped = self.loop_stack.pop()
            assert popped is None
            return [tast.Switch(ast.varname, utype, cases)]

        raise NotImplementedError(ast)

    def do_block(self, block: List[uast.Statement]) -> List[tast.Statement]:
        result = []
        for statement in block:
            result.extend(self.do_statement(statement))
        return result


def _create_to_string_method(class_type: tast.Type) -> uast.FuncDef:
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

    return uast.FuncDef(
        "to_string",
        [],
        uast.Type("Str", None),
        [uast.Return(uast.StringFormatJoin(strings))],
    )


class _FileTyper:
    def __init__(self) -> None:
        self._types = builtin_types.copy()
        self._generic_types = builtin_generic_types.copy()
        self.variables = builtin_variables.copy()

        # Union members don't need to exist when union is defined (allows nestedness)
        self.union_laziness: Dict[UnionType, List[uast.Type]] = {}

    def get_type(self, raw_type: uast.Type) -> tast.Type:
        if raw_type.generic is None:
            return self._types[raw_type.name]
        return self._generic_types[raw_type.name].get_type(
            self.get_type(raw_type.generic)
        )

    def _do_funcdef(self, funcdef: uast.FuncDef, create_variable: bool) -> tast.FuncDef:
        functype = FunctionType(
            [self.get_type(typ) for typ, nam in funcdef.args],
            None if funcdef.returntype is None else self.get_type(funcdef.returntype),
        )
        if create_variable:
            assert funcdef.name not in self.variables, (
                funcdef.name,
                self.variables.keys(),
            )
            self.variables[funcdef.name] = functype

        local_vars = self.variables.copy()
        for (typename, argname), the_type in zip(funcdef.args, functype.argtypes):
            assert argname not in local_vars
            local_vars[argname] = the_type

        typer = _FunctionOrMethodTyper(self, local_vars)
        body = typer.do_block(funcdef.body)
        return tast.FuncDef(
            funcdef.name,
            functype,
            [argname for typename, argname in funcdef.args],
            body,
            typer.reflist,
        )

    def do_toplevel_statement(
        self,
        top_statement: uast.ToplevelStatement,
    ) -> tast.ToplevelStatement:
        if isinstance(top_statement, uast.FuncDef):
            return self._do_funcdef(top_statement, create_variable=True)

        if isinstance(top_statement, uast.ClassDef):
            assert top_statement.type.generic is None
            classtype = Type(top_statement.type.name, True)
            assert top_statement.type.name not in self._types
            self._types[top_statement.type.name] = classtype
            classtype.members.extend(
                (self.get_type(typ), nam) for typ, nam in top_statement.members
            )
            classtype.constructor_argtypes = [typ for typ, nam in classtype.members]

            if "to_string" not in (method.name for method in top_statement.body):
                top_statement.body.insert(
                    0,
                    _create_to_string_method(classtype),
                )

            typed_method_defs = []
            for method_def in top_statement.body:
                method_def.args.insert(0, (top_statement.type, "self"))
                typed_def = self._do_funcdef(method_def, create_variable=False)
                classtype.methods[method_def.name] = typed_def.type
                typed_method_defs.append(typed_def)

            return tast.ClassDef(classtype, typed_method_defs)

        if isinstance(top_statement, uast.UnionDef):
            union_type = UnionType(top_statement.name)
            self._types[top_statement.name] = union_type
            self.union_laziness[union_type] = top_statement.type_members
            return tast.UnionDef(union_type)

        raise NotImplementedError(top_statement)

    def post_process_union(self, union: UnionType) -> List[Type]:
        if union.type_members is None:
            types = self.union_laziness.pop(union)
            union.set_type_members([self.get_type(t) for t in types])

        assert union.type_members is not None
        return union.type_members


def convert_program(
    program: List[uast.ToplevelStatement],
) -> List[tast.ToplevelStatement]:
    typer = _FileTyper()
    result = [typer.do_toplevel_statement(top) for top in program]
    for key in list(typer.union_laziness):
        typer.post_process_union(key)
    return result
