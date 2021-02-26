from typing import IO, Callable, Iterable, Optional, Tuple, TypeVar, Union, List
import io

import compiler.typed_ast as tast
from compiler.types import INT, ClassType, Type

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
        elif isinstance(the_type, ClassType):
            self.file.write(f"struct class_{the_type.name} *")
        elif the_type is None:
            self.file.write("void ")
        else:
            raise NotImplementedError(the_type)


class _FunctionEmitter(_Emitter):
    def __init__(self, file: IO[str], funcdef: tast.FuncDef):
        super().__init__(file)
        self.funcdef = funcdef

    def _emit_call(self, ast: Union[tast.ReturningCall, tast.VoidCall]) -> None:
        self.file.write("(")

        if isinstance(ast.func, tast.GetMethod):
            args = [ast.func.obj] + ast.args
        else:
            args = ast.args

        temps = []
        for arg in args:
            temp = self.get_temp_var(arg.type)
            temps.append(temp)
            self.file.write(f"{temp} = (")
            self._emit_expression(arg)
            self.file.write("), ")

        if isinstance(ast.func, tast.GetMethod):
            assert isinstance(ast.func.obj.type, ClassType)
            self.file.write(f"meth_{ast.func.obj.type.name}_{ast.func.name}")
        else:
            self._emit_expression(ast.func)

        self.file.write("(" + ",".join(temps) + "))")

    def _emit_expression(self, ast: tast.Expression) -> None:
        if isinstance(ast, tast.IntConstant):
            self.file.write(f"((int64_t){ast.value}LL)")
        elif isinstance(ast, tast.ReturningCall):
            self._emit_call(ast)
        elif isinstance(ast, tast.GetVar):
            self.file.write("var_" + ast.varname)
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
        elif isinstance(ast, tast.GetMethod):
            # This should return some kind of partial function, which isn't possible yet
            raise NotImplementedError
        else:
            raise NotImplementedError(ast)

    def _emit_statement(self, ast: tast.Statement) -> None:
        if isinstance(ast, tast.LetStatement):
            self._emit_type(ast.value.type)
            self.file.write(f"var_{ast.varname} = ")
            self._emit_expression(ast.value)
        elif isinstance(ast, (tast.ReturningCall, tast.VoidCall)):
            self._emit_call(ast)
        elif isinstance(ast, tast.DecRefObject):
            self.file.write("decref(")
            self._emit_expression(ast.value)
            self.file.write(")")
        elif isinstance(ast, tast.ReturnStatement):
            if ast.value is not None:
                self.file.write("retval = ")
                self._emit_expression(ast.value)
                self.file.write(";")
                if ast.value.type.refcounted:
                    self.file.write("incref(retval);")
            self.file.write("goto out")
        else:
            raise NotImplementedError(ast)
        self.file.write(";\n\t")

    def _emit_body(self, c_name: str) -> None:
        funcdef = self.funcdef  # TODO: remove

        if funcdef.type.returntype is not None:
            self._emit_type(funcdef.type.returntype)
            self.file.write("retval;\n\t")
        for refname, reftype in funcdef.refs:
            self._emit_type(reftype)
            self.file.write(f"{refname} = NULL;\n\t")

        for statement in funcdef.body:
            self._emit_statement(statement)

        # avoid problem with 'out:' being last thing in function
        self.file.write("out: (void)0;\n\t")
        for refname, reftype in reversed(funcdef.refs):
            self.file.write(f"if ({refname}) decref({refname});\n\t")
        if funcdef.type.returntype is not None:
            self.file.write("return retval;\n\t")

    def run(self, c_name: str) -> None:
        funcdef = self.funcdef  # TODO: remove
        self._emit_type(funcdef.type.returntype)
        if funcdef.argnames:
            self.file.write(c_name)
            self.file.write("(")
            self._emit_commasep(
                zip(funcdef.type.argtypes, funcdef.argnames), self._emit_arg_def
            )
            self.file.write(")")
        else:
            self.file.write(c_name)
            self.file.write("(void)")
        self.file.write("{\n\t")

        # First figure out what temp vars are needed
        actual_file = self.file
        self.file = io.StringIO()
        temps: List[Type] = []
        self.get_temp_var = lambda t: (f"temp{len(temps)}", temps.append(t))[0]
        self._emit_body(c_name)

        # Add temporary vars
        self.file = actual_file
        for i, vartype in enumerate(temps):
            self._emit_type(vartype)
            self.file.write(f"temp{i};\n\t")

        # Run for real
        iterator = (f"temp{i}" for i in range(len(temps)))
        self.get_temp_var = (lambda t: next(iterator))
        self._emit_body(c_name)

        self.file.write("\n}\n")


class _TopLevelEmitter(_Emitter):
    def emit_toplevel_statement(self, top_statement: tast.ToplevelStatement) -> None:
        if isinstance(top_statement, tast.FuncDef):
            _FunctionEmitter(self.file, top_statement).run(
                "var_" + top_statement.name
            )

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
                _FunctionEmitter(self.file,method).run(
                    f"meth_{top_statement.type.name}_{method.name}"
                )

        else:
            raise NotImplementedError(top_statement)


def emit_toplevel_statement(
    file: IO[str], top_statement: tast.ToplevelStatement
) -> None:
    _TopLevelEmitter(file).emit_toplevel_statement(top_statement)
