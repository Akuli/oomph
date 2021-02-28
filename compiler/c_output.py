from typing import IO, Dict, Iterator, List, Optional, Tuple, TypeVar, Union

import compiler.typed_ast as tast
from compiler.types import BOOL, FLOAT, INT, ClassType, Type

_T = TypeVar("_T")


class _Emitter:
    def _emit_type(self, the_type: Optional[Type]) -> str:
        if the_type is INT:
            return "int64_t"
        if the_type is FLOAT:
            return "double"
        if the_type is BOOL:
            return "bool"
        if isinstance(the_type, ClassType):
            return f"struct class_{the_type.name} *"
        if the_type is None:
            return "void"
        raise NotImplementedError(the_type)


class _FunctionEmitter(_Emitter):
    name_mapping: Dict[str, str]  # values are names in c
    loop_counter: int

    def __init__(self, c_name: str, funcdef: tast.FuncDef):
        super().__init__()
        self.c_name = c_name
        self.funcdef = funcdef

        self.local_vars: List[Tuple[Type, str]] = []
        self.local_var_iter: Optional[Iterator[Tuple[Type, str]]] = None

    # This thing goes over function ast twice, resetting before each pass
    def reset(self) -> None:
        self.name_mapping = {}
        self.loop_counter = 0

    def get_local_var(self, the_type: Type, name_hint: str) -> str:
        if self.local_var_iter is None:
            # First pass: create temporary variables
            name = f"{name_hint}_{len(self.local_vars)}"
            self.local_vars.append((the_type, name))
        else:
            # Second pass: use variables created in first pass
            var_type, name = next(self.local_var_iter)
            assert var_type == the_type
        return name

    def _emit_call(self, ast: Union[tast.ReturningCall, tast.VoidCall]) -> str:
        if isinstance(ast.func, tast.GetMethod):
            args = [ast.func.obj] + ast.args
        else:
            args = ast.args

        if isinstance(ast.func, tast.GetMethod):
            func = f"meth_{ast.func.obj.type.name}_{ast.func.name}"
        else:
            func = self._emit_expression(ast.func)

        # In C, argument order is not guaranteed, but evaluation of comma
        # expressions is guaranteed. Comma-expression-evaluate all arguments
        # and put them to temporary variables, then do the call with the
        # temporary variables as arguments.
        varnames = [self.get_local_var(arg.type, "arg") for arg in args]

        return (
            "("
            + " ".join(
                f"{var} = ({self._emit_expression(arg)}),"
                for var, arg in zip(varnames, args)
            )
            + f"{func}({','.join(varnames)}))"
        )

    def _emit_expression(self, ast: tast.Expression) -> str:
        if isinstance(ast, tast.IntConstant):
            return f"((int64_t){ast.value}LL)"
        if isinstance(ast, tast.FloatConstant):
            return f"({ast.value})"
        if isinstance(ast, tast.BoolConstant):
            return "true" if ast.value else "false"
        if isinstance(ast, tast.ReturningCall):
            return self._emit_call(ast)
        if isinstance(ast, tast.GetVar):
            return self.name_mapping.get(ast.varname, f"var_{ast.varname}")
        if isinstance(ast, tast.Constructor):
            return "ctor_" + ast.class_to_construct.name
        if isinstance(ast, tast.SetRef):
            return f"({ast.refname} = {self._emit_expression(ast.value)})"
        if isinstance(ast, tast.GetAttribute):
            return f"(({self._emit_expression(ast.obj)})->memb_{ast.attribute})"
        if isinstance(ast, tast.IntToFloat):
            return f"((float) {self._emit_expression(ast.value)} )"
        if isinstance(
            ast,
            (
                tast.NumberAdd,
                tast.NumberSub,
                tast.NumberMul,
                tast.NumberEqual,
                tast.FloatDiv,
                tast.BoolAnd,
                tast.BoolOr,
            ),
        ):
            lhs = self._emit_expression(ast.lhs)
            rhs = self._emit_expression(ast.rhs)
            if isinstance(ast, tast.NumberAdd):
                return f"({lhs} + {rhs})"
            if isinstance(ast, tast.NumberSub):
                return f"({lhs} - {rhs})"
            if isinstance(ast, tast.NumberMul):
                return f"({lhs} * {rhs})"
            if isinstance(ast, tast.NumberEqual):
                return f"({lhs} == {rhs})"
            if isinstance(ast, tast.FloatDiv):
                return f"({lhs} / {rhs})"
            if isinstance(ast, tast.BoolAnd):
                return f"({lhs} && {rhs})"
            if isinstance(ast, tast.BoolOr):
                return f"({lhs} || {rhs})"
            raise NotImplementedError
        if isinstance(ast, tast.BoolNot):
            return f"(! {self._emit_expression(ast.obj)} )"
        if isinstance(ast, tast.NumberNegation):
            return f"(- {self._emit_expression(ast.obj)} )"
        if isinstance(ast, tast.GetMethod):
            # This should return some kind of partial function, which isn't possible yet
            raise NotImplementedError(
                "method objects without immediate calling don't work yet"
            )
        raise NotImplementedError(ast)

    def _emit_label(self, name: str) -> str:
        # It's invalid c syntax to end a block with a label, (void)0 fixes
        return f"{name}: (void)0;\n\t"

    def _emit_statement(self, ast: tast.Statement) -> str:
        if isinstance(ast, tast.CreateLocalVar):
            var = self.get_local_var(ast.value.type, ast.varname)
            assert ast.varname not in self.name_mapping
            self.name_mapping[ast.varname] = var
            return f"{var} = {self._emit_expression(ast.value)};\n\t"

        if isinstance(ast, tast.SetLocalVar):
            return f"{self.name_mapping[ast.varname]} = {self._emit_expression(ast.value)};\n\t"

        if isinstance(ast, (tast.ReturningCall, tast.VoidCall)):
            return self._emit_call(ast) + ";\n\t"

        if isinstance(ast, tast.DecRef):
            # TODO: decref could be a macro
            var = self.get_local_var(ast.value.type, "decreffing_var")
            return f"{var} = {self._emit_expression(ast.value)}; decref({var});\n\t"

        if isinstance(ast, tast.Return):
            if ast.value is not None and ast.value.type.refcounted:
                return f"retval = {self._emit_expression(ast.value)}; incref(retval); goto out;\n\t"
            if ast.value is not None:
                return f"retval = {self._emit_expression(ast.value)}; goto out;\n\t"
            return "goto out;\n\t"

        if isinstance(ast, tast.If):
            return (
                ("if (%s) {\n\t" % self._emit_expression(ast.condition))
                + "".join(self._emit_statement(s) for s in ast.then)
                + "} else {\n\t"
                + "".join(self._emit_statement(s) for s in ast.otherwise)
                + "}\n\t"
            )

        if isinstance(ast, tast.Loop):
            # Can't use C's for loop because it's limited to one statement
            return (
                "".join(self._emit_statement(s) for s in ast.init)
                + ("while (%s) {\n\t" % self._emit_expression(ast.cond))
                + "".join(self._emit_statement(s) for s in ast.body)
                + self._emit_label(ast.loop_id)
                + "".join(self._emit_statement(s) for s in ast.incr)
                + "}\n\t"
            )

        if isinstance(ast, tast.Continue):
            # Can't use C's continue because continue must run condition
            return f"goto {ast.loop_id};\n\t"

        if isinstance(ast, tast.Break):
            return "break;\n\t"

        raise NotImplementedError(ast)

    def _emit_body(self) -> str:
        return (
            (
                ""
                if self.funcdef.type.returntype is None
                else f"{self._emit_type(self.funcdef.type.returntype)} retval;\n\t"
            )
            + "".join(
                f"{self._emit_type(reftype)} {refname} = NULL;\n\t"
                for refname, reftype in self.funcdef.refs
            )
            + "".join(
                self._emit_statement(statement) for statement in self.funcdef.body
            )
            + self._emit_label("out")
            + "".join(
                f"if ({refname}) decref({refname});\n\t"
                for refname, reftype in reversed(self.funcdef.refs)
            )
            + ("" if self.funcdef.type.returntype is None else "return retval;\n\t")
        )

    def run(self) -> str:
        beginning = (
            f"{self._emit_type(self.funcdef.type.returntype)} {self.c_name}("
            + (
                ",".join(
                    f"{self._emit_type(the_type)} var_{name}"
                    for the_type, name in zip(
                        self.funcdef.type.argtypes, self.funcdef.argnames
                    )
                )
                or "void"
            )
            + ") {\n\t"
        )

        # First figure out what temp vars are needed
        self.reset()
        assert not self.local_vars
        self._emit_body()

        # Add temporary vars
        var_decls = "".join(
            f"{self._emit_type(vartype)} {name};\n\t"
            for vartype, name in self.local_vars
        )

        # Run for real
        self.reset()
        self.local_var_iter = iter(self.local_vars)
        return beginning + var_decls + self._emit_body() + "\n}\n"


class _TopLevelEmitter(_Emitter):
    def emit_toplevel_statement(self, top_statement: tast.ToplevelStatement) -> str:
        if isinstance(top_statement, tast.FuncDef):
            return _FunctionEmitter("var_" + top_statement.name, top_statement).run()

        if isinstance(top_statement, tast.ClassDef):
            return (
                # struct
                ("struct class_%s {\n" % top_statement.type.name)
                + "\tREFCOUNT_HEADER\n\t"
                + "".join(
                    f"{self._emit_type(the_type)} memb_{name};\n\t"
                    for the_type, name in top_statement.type.members
                )
                + "\n};\n"
                # constructor
                + f"{self._emit_type(top_statement.type)} ctor_{top_statement.type.name}("
                + ",".join(
                    f"{self._emit_type(the_type)} var_{name}"
                    for the_type, name in top_statement.type.members
                )
                + ") {\n\t"
                + f"{self._emit_type(top_statement.type)} obj = malloc(sizeof(*obj));\n\t"
                + "obj->refcount = 1;\n\t"
                + "".join(
                    f"obj->memb_{name} = var_{name};\n\t"
                    for the_type, name in top_statement.type.members
                )
                + "return obj;\n}\n"
                # methods
                + "".join(
                    _FunctionEmitter(
                        f"meth_{top_statement.type.name}_{method.name}", method
                    ).run()
                    for method in top_statement.body
                )
            )

        raise NotImplementedError(top_statement)


def emit_toplevel_statement(
    file: IO[str], top_statement: tast.ToplevelStatement
) -> None:
    file.write(_TopLevelEmitter().emit_toplevel_statement(top_statement))
