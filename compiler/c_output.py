import os
from typing import (
    IO,
    Callable,
    Dict,
    Iterable,
    Iterator,
    List,
    Optional,
    Tuple,
    TypeVar,
    Union,
)

import compiler.typed_ast as tast
from compiler.types import BOOL, FLOAT, INT, ClassType, Type

_T = TypeVar("_T")


class _Emitter:
    def __init__(self, file: IO[str]):
        self.file = file

    def _emit_commasep(
        self, items: Iterable[_T], callback: Callable[[_T], object]
    ) -> None:
        first = True
        for item in items:
            if not first:
                self.file.write(",")
            first = False
            callback(item)

    def _emit_arg_def(self, pair: Tuple[Type, str]) -> None:
        the_type, name = pair
        self._emit_type(the_type)
        self.file.write("var_" + name)

    def _emit_type(self, the_type: Optional[Type]) -> None:
        if the_type is INT:
            self.file.write("int64_t ")
        elif the_type is FLOAT:
            self.file.write("double ")
        elif the_type is BOOL:
            self.file.write("bool ")
        elif isinstance(the_type, ClassType):
            self.file.write(f"struct class_{the_type.name} *")
        elif the_type is None:
            self.file.write("void ")
        else:
            raise NotImplementedError(the_type)


class _FunctionEmitter(_Emitter):
    loop_counter: int

    def __init__(self, file: IO[str], c_name: str, funcdef: tast.FuncDef):
        super().__init__(file)
        self.c_name = c_name
        self.funcdef = funcdef

        self.local_vars: List[Tuple[Type, str]] = []
        self.local_var_iter: Optional[Iterator[Tuple[Type, str]]] = None
        self.name_mapping: Dict[str, str] = {}  # values are names in c

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

    def _emit_call(self, ast: Union[tast.ReturningCall, tast.VoidCall]) -> None:
        self.file.write("(")

        if isinstance(ast.func, tast.GetMethod):
            args = [ast.func.obj] + ast.args
        else:
            args = ast.args

        # In C, argument order is not guaranteed, but evaluation of comma
        # expressions is guaranteed. Comma-expression-evaluate all arguments
        # and put them to temporary variables, then do the call with the
        # temporary variables as arguments.
        local_var_names = []
        for arg in args:
            temp = self.get_local_var(arg.type, "arg")
            local_var_names.append(temp)
            self.file.write(f"{temp} = (")
            self._emit_expression(arg)
            self.file.write("), ")

        if isinstance(ast.func, tast.GetMethod):
            self.file.write(f"meth_{ast.func.obj.type.name}_{ast.func.name}")
        else:
            self._emit_expression(ast.func)

        self.file.write("(" + ",".join(local_var_names) + "))")

    def _emit_expression(self, ast: tast.Expression) -> None:
        if isinstance(ast, tast.IntConstant):
            self.file.write(f"((int64_t){ast.value}LL)")
        elif isinstance(ast, tast.FloatConstant):
            self.file.write(f"({ast.value})")
        elif isinstance(ast, tast.BoolConstant):
            self.file.write("true" if ast.value else "false")
        elif isinstance(ast, tast.ReturningCall):
            self._emit_call(ast)
        elif isinstance(ast, tast.GetVar):
            self.file.write(self.name_mapping.get(ast.varname, f"var_{ast.varname}"))
        elif isinstance(ast, tast.Constructor):
            self.file.write("ctor_" + ast.class_to_construct.name)
        elif isinstance(ast, tast.SetRef):
            self.file.write(f"({ast.refname} = ")
            self._emit_expression(ast.value)
            self.file.write(")")
        elif isinstance(ast, tast.GetAttribute):
            self.file.write("((")
            self._emit_expression(ast.obj)
            self.file.write(f")->memb_{ast.attribute})")
        elif isinstance(ast, tast.IntToFloat):
            self.file.write("((float)")
            self._emit_expression(ast.value)
            self.file.write(")")
        elif isinstance(
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
            self.file.write("(")
            self._emit_expression(ast.lhs)
            if isinstance(ast, tast.NumberAdd):
                self.file.write("+")
            elif isinstance(ast, tast.NumberSub):
                self.file.write("-")
            elif isinstance(ast, tast.NumberMul):
                self.file.write("*")
            elif isinstance(ast, tast.NumberEqual):
                self.file.write("==")
            elif isinstance(ast, tast.FloatDiv):
                self.file.write("/")
            elif isinstance(ast, tast.BoolAnd):
                self.file.write("&&")
            elif isinstance(ast, tast.BoolOr):
                self.file.write("||")
            else:
                raise NotImplementedError
            # https://github.com/python/mypy/issues/10146
            self._emit_expression(ast.rhs)  # type: ignore
            self.file.write(")")
        elif isinstance(ast, tast.BoolNot):
            self.file.write("(!")
            self._emit_expression(ast.obj)
            self.file.write(")")
        elif isinstance(ast, tast.NumberNegation):
            self.file.write("(-")
            self._emit_expression(ast.obj)
            self.file.write(")")
        elif isinstance(ast, tast.GetMethod):
            # This should return some kind of partial function, which isn't possible yet
            raise NotImplementedError(
                "method objects without immediate calling don't work yet"
            )
        else:
            raise NotImplementedError(ast)

    def _emit_statement(self, ast: tast.Statement) -> None:
        if isinstance(ast, tast.CreateLocalVar):
            var = self.get_local_var(ast.value.type, ast.varname)
            if ast.varname in self.name_mapping:
                assert self.name_mapping[ast.varname] == var
            else:
                self.name_mapping[ast.varname] = var
            self.file.write(f"{var} = ")
            self._emit_expression(ast.value)
            self.file.write(";\n\t")

        elif isinstance(ast, tast.SetLocalVar):
            self.file.write(f"{self.name_mapping[ast.varname]} = ")
            self._emit_expression(ast.value)
            self.file.write(";\n\t")

        elif isinstance(ast, (tast.ReturningCall, tast.VoidCall)):
            self._emit_call(ast)

        elif isinstance(ast, tast.DecRef):
            var = self.get_local_var(ast.value.type, "decreffing_var")
            self.file.write(f"{var} = ")
            self._emit_expression(ast.value)
            self.file.write(f"; if({var}) decref({var});\n\t")

        elif isinstance(ast, tast.Return):
            if ast.value is not None:
                self.file.write("retval = ")
                self._emit_expression(ast.value)
                self.file.write(";")
                if ast.value.type.refcounted:
                    self.file.write("incref(retval);")
            self.file.write("goto out;\n\t")

        elif isinstance(ast, tast.If):
            self.file.write("if (")
            self._emit_expression(ast.condition)
            self.file.write(") {\n\t")
            for statement in ast.then:
                self._emit_statement(statement)
            self.file.write("} else {\n\t")
            for statement in ast.otherwise:
                self._emit_statement(statement)
            self.file.write("}\n\t")
            return  # no semicolon

        elif isinstance(ast, tast.Loop):
            # Can't use C's for loop because it's limited to one statement
            for statement in ast.init:
                self._emit_statement(statement)
            self.file.write('while(')
            self._emit_expression(ast.cond)
            self.file.write('){\n\t')
            for statement in ast.body + ast.incr:
                self._emit_statement(statement)
            self.file.write('}\n\t')
            return  # no semicolon

        else:
            raise NotImplementedError(ast)

        self.file.write(";\n\t")

    def _emit_body(self, c_name: str) -> None:
        if self.funcdef.type.returntype is not None:
            self._emit_type(self.funcdef.type.returntype)
            self.file.write("retval;\n\t")
        for refname, reftype in self.funcdef.refs:
            self._emit_type(reftype)
            self.file.write(f"{refname} = NULL;\n\t")

        for statement in self.funcdef.body:
            self._emit_statement(statement)

        # avoid problem with 'out:' being last thing in function
        self.file.write("out: (void)0;\n\t")
        for refname, reftype in reversed(self.funcdef.refs):
            self.file.write(f"if ({refname}) decref({refname});\n\t")
        if self.funcdef.type.returntype is not None:
            self.file.write("return retval;\n\t")

    def run(self) -> None:
        self._emit_type(self.funcdef.type.returntype)
        if self.funcdef.argnames:
            self.file.write(self.c_name)
            self.file.write("(")
            self._emit_commasep(
                zip(self.funcdef.type.argtypes, self.funcdef.argnames),
                self._emit_arg_def,
            )
            self.file.write(")")
        else:
            self.file.write(self.c_name)
            self.file.write("(void)")
        self.file.write("{\n\t")

        # First figure out what temp vars are needed
        self.loop_counter = 0
        assert not self.local_vars
        actual_file = self.file
        with open(os.devnull, "w") as self.file:
            self._emit_body(self.c_name)
        self.file = actual_file

        # Add temporary vars
        for vartype, name in self.local_vars:
            self._emit_type(vartype)
            self.file.write(f"{name};\n\t")

        # Run for real
        self.loop_counter = 0
        self.local_var_iter = iter(self.local_vars)
        self._emit_body(self.c_name)
        self.file.write("\n}\n")


class _TopLevelEmitter(_Emitter):
    def emit_toplevel_statement(self, top_statement: tast.ToplevelStatement) -> None:
        if isinstance(top_statement, tast.FuncDef):
            _FunctionEmitter(
                self.file, "var_" + top_statement.name, top_statement
            ).run()

        elif isinstance(top_statement, tast.ClassDef):
            # struct
            self.file.write("struct class_%s {\n" % top_statement.type.name)
            self.file.write("\tREFCOUNT_HEADER\n\t")
            for the_type, name in top_statement.type.members:
                self._emit_type(the_type)
                self.file.write("memb_" + name + ";\n\t")
            self.file.write("\n};\n")

            # constructor
            self._emit_type(top_statement.type)
            self.file.write(f"ctor_{top_statement.type.name}(")
            self._emit_commasep(top_statement.type.members, self._emit_arg_def)
            self.file.write(") {\n\t")
            self._emit_type(top_statement.type)
            self.file.write("obj = malloc(sizeof(*obj));\n")
            self.file.write("\tobj->refcount = 1;\n")
            for the_type, name in top_statement.type.members:
                self.file.write(f"\tobj->memb_{name} = var_{name};\n")
            self.file.write("\treturn obj;\n}\n")

            # methods
            for method in top_statement.body:
                _FunctionEmitter(
                    self.file, f"meth_{top_statement.type.name}_{method.name}", method
                ).run()

        else:
            raise NotImplementedError(top_statement)


def emit_toplevel_statement(
    file: IO[str], top_statement: tast.ToplevelStatement
) -> None:
    _TopLevelEmitter(file).emit_toplevel_statement(top_statement)
