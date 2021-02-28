import itertools
from typing import Dict, List, Tuple, Union

from compiler import typed_ast as tast
from compiler import untyped_ast as uast
from compiler.types import (
    BOOL,
    FLOAT,
    INT,
    STRING,
    ClassType,
    FunctionType,
    Type,
    global_variables,
)

_special_funcs = {
    "bool_and": FunctionType([BOOL, BOOL], BOOL),
    "bool_eq": FunctionType([BOOL, BOOL], BOOL),
    "bool_false": FunctionType([], BOOL),
    "bool_not": FunctionType([BOOL], BOOL),
    "bool_or": FunctionType([BOOL, BOOL], BOOL),
    "bool_true": FunctionType([], BOOL),
    "float_add": FunctionType([FLOAT, FLOAT], FLOAT),
    "float_div": FunctionType([FLOAT, FLOAT], FLOAT),
    "float_eq": FunctionType([FLOAT, FLOAT], BOOL),
    "float_mul": FunctionType([FLOAT, FLOAT], FLOAT),
    "float_neg": FunctionType([FLOAT], FLOAT),
    "float_sub": FunctionType([FLOAT, FLOAT], FLOAT),
    "int2float": FunctionType([INT], FLOAT),
    "int_add": FunctionType([INT, INT], INT),
    "int_eq": FunctionType([INT, INT], BOOL),
    "int_mod": FunctionType([INT, INT], INT),
    "int_mul": FunctionType([INT, INT], INT),
    "int_neg": FunctionType([INT], INT),
    "int_sub": FunctionType([INT, INT], INT),
    "string_concat": FunctionType([STRING, STRING], STRING),
}


class _FunctionOrMethodTyper:
    def __init__(self, variables: Dict[str, Type], types: Dict[str, Type]):
        self.variables = variables
        self.types = types
        self.reflist: List[Tuple[str, Type]] = []
        self.loop_stack: List[str] = []
        self.loop_counter = 0
        self.ref_names = (f"ref{n}" for n in itertools.count())

    def create_returning_call(
        self, func: tast.Expression, args: List[tast.Expression]
    ) -> Union[tast.SetRef, tast.ReturningCall]:
        result = tast.ReturningCall(func, args)
        if result.type.refcounted:  # TODO: what else needs ref holding?
            refname = next(self.ref_names)
            self.reflist.append((refname, result.type))
            return tast.SetRef(result.type, refname, result)
        return result

    def create_special_returning_call(
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
        args = [self.do_expression(arg) for arg in ast.args]
        assert len(args) == len(func.type.argtypes)
        for arg, argtype in zip(args, func.type.argtypes):
            assert arg.type == argtype, (arg.type, argtype)

        if func.type.returntype is None:
            return tast.VoidCall(func, args)
        return self.create_returning_call(func, args)

    def do_binary_op(self, ast: uast.BinaryOperator) -> tast.Expression:
        if ast.op == "!=":
            return self.create_special_returning_call(
                "bool_not",
                [self.do_binary_op(uast.BinaryOperator(ast.lhs, "==", ast.rhs))],
            )

        lhs = self.do_expression(ast.lhs)
        rhs = self.do_expression(ast.rhs)

        if lhs.type is STRING and ast.op == "+" and rhs.type is STRING:
            # TODO: add something to make a+b+c more efficient than (a+b)+c
            return self.create_special_returning_call("string_concat", [lhs, rhs])

        if lhs.type is INT and ast.op in {"+", "-", "*", "mod"} and rhs.type is INT:
            return self.create_special_returning_call(
                {
                    "+": "int_add",
                    "-": "int_sub",
                    "*": "int_mul",
                    "mod": "int_mod",
                }[ast.op],
                [lhs, rhs],
            )

        if lhs.type is INT and ast.op == "/" and rhs.type is INT:
            lhs = self.create_special_returning_call("int2float", [lhs])
            rhs = self.create_special_returning_call("int2float", [rhs])
        if lhs.type is INT and rhs.type is FLOAT:
            lhs = self.create_special_returning_call("int2float", [lhs])
        if lhs.type is FLOAT and rhs.type is INT:
            rhs = self.create_special_returning_call("int2float", [rhs])

        if lhs.type is FLOAT and ast.op in {"+", "-", "*", "/"} and rhs.type is FLOAT:
            return self.create_special_returning_call(
                {
                    "+": "float_add",
                    "-": "float_sub",
                    "*": "float_mul",
                    "/": "float_div",
                }[ast.op],
                [lhs, rhs],
            )

        if lhs.type is BOOL and ast.op == "and" and rhs.type is BOOL:
            return self.create_special_returning_call("bool_and", [lhs, rhs])
        if lhs.type is BOOL and ast.op == "or" and rhs.type is BOOL:
            return self.create_special_returning_call("bool_or", [lhs, rhs])
        if lhs.type is BOOL and ast.op == "==" and rhs.type is BOOL:
            return self.create_special_returning_call("bool_eq", [lhs, rhs])
        if lhs.type is INT and ast.op == "==" and rhs.type is INT:
            return self.create_special_returning_call("int_eq", [lhs, rhs])
        if lhs.type is FLOAT and ast.op == "==" and rhs.type is FLOAT:
            # Float equality sucks, but maybe it can be useful for something
            return self.create_special_returning_call("float_eq", [lhs, rhs])
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
                result = self.create_special_returning_call(
                    "string_concat", [result, self.do_expression_to_string(part)]
                )
            return result
        if isinstance(ast, uast.Call):
            call = self.do_call(ast)
            assert not isinstance(call, tast.VoidCall)
            return call
        if isinstance(ast, uast.GetVar):
            if ast.varname == "true":
                return self.create_special_returning_call("bool_true", [])
            if ast.varname == "false":
                return self.create_special_returning_call("bool_false", [])
            return tast.GetVar(self.variables[ast.varname], ast.varname)
        if isinstance(ast, uast.UnaryOperator):
            obj = self.do_expression(ast.obj)
            if obj.type is BOOL and ast.op == "not":
                return self.create_special_returning_call("bool_not", [obj])
            if obj.type is INT and ast.op == "-":
                return self.create_special_returning_call("int_neg", [obj])
            if obj.type is FLOAT and ast.op == "-":
                return self.create_special_returning_call("float_neg", [obj])
            raise NotImplementedError(f"{ast.op} {obj.type}")
        if isinstance(ast, uast.BinaryOperator):
            return self.do_binary_op(ast)
        if isinstance(ast, uast.Constructor):
            klass = self.types[ast.type]
            assert isinstance(klass, ClassType)
            return tast.Constructor(klass.get_constructor_type(), klass)
        if isinstance(ast, uast.GetAttribute):
            obj = self.do_expression(ast.obj)
            try:
                return tast.GetMethod(obj, ast.attribute)
            except KeyError:
                return tast.GetAttribute(obj, ast.attribute)
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
            return [tast.Continue(self.loop_stack[-1])]

        if isinstance(ast, uast.Break):
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
                self.create_special_returning_call("bool_true", [])
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

            return [tast.Loop(loop_id, init, cond, incr, body)]

        raise NotImplementedError(ast)

    def do_block(self, block: List[uast.Statement]) -> List[tast.Statement]:
        result = []
        for statement in block:
            result.extend(self.do_statement(statement))
        return result


def _do_funcdef(
    variables: Dict[str, Type],
    types: Dict[str, Type],
    funcdef: uast.FuncDef,
    create_variable: bool,
) -> tast.FuncDef:
    functype = FunctionType(
        [types[typename] for typename, argname in funcdef.args],
        None if funcdef.returntype is None else types[funcdef.returntype],
    )
    if create_variable:
        assert funcdef.name not in variables, (funcdef.name, variables.keys())
        variables[funcdef.name] = functype

    local_vars = variables.copy()
    for (typename, argname), the_type in zip(funcdef.args, functype.argtypes):
        assert argname not in local_vars
        local_vars[argname] = the_type

    typer = _FunctionOrMethodTyper(local_vars, types)
    body = typer.do_block(funcdef.body)
    return tast.FuncDef(
        funcdef.name,
        functype,
        [argname for typename, argname in funcdef.args],
        body,
        typer.reflist,
    )


def _do_toplevel_statement(
    variables: Dict[str, Type],
    types: Dict[str, Type],
    top_statement: uast.ToplevelStatement,
) -> tast.ToplevelStatement:
    if isinstance(top_statement, uast.FuncDef):
        return _do_funcdef(variables, types, top_statement, create_variable=True)

    if isinstance(top_statement, uast.ClassDef):
        classtype = ClassType(top_statement.name, True, {}, [])
        assert top_statement.name not in types
        types[top_statement.name] = classtype
        classtype.members.extend(
            (types[typename], membername)
            for typename, membername in top_statement.members
        )

        typed_method_defs = []
        for method_def in top_statement.body:
            method_def.args.insert(0, (top_statement.name, "self"))
            typed_def = _do_funcdef(variables, types, method_def, create_variable=False)
            classtype.methods[method_def.name] = typed_def.type
            typed_method_defs.append(typed_def)

        return tast.ClassDef(classtype, typed_method_defs)

    raise NotImplementedError(top_statement)


def convert_program(
    program: List[uast.ToplevelStatement],
) -> List[tast.ToplevelStatement]:
    types: Dict[str, Type] = {"int": INT, "float": FLOAT, "bool": BOOL, "Str": STRING}
    variables = global_variables.copy()
    return [
        _do_toplevel_statement(variables, types, toplevel_statement)
        for toplevel_statement in program
    ]
