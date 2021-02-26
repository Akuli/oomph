from functools import partial
from typing import IO, Callable, Iterable, Optional, Tuple, TypeVar, Union

import compiler.typed_ast as tast
from compiler.types import INT, ClassType, Type

_T = TypeVar("_T")


def _emit_commasep(
    file: IO[str], items: Iterable[_T], callback: Callable[[_T], object]
) -> None:
    first = True
    for item in items:
        if not first:
            file.write(",")
        first = False
        callback(item)


def _emit_call(file: IO[str], ast: Union[tast.ReturningCall, tast.VoidCall]) -> None:
    file.write("(")
    if isinstance(ast.func, tast.GetMethod):
        assert isinstance(ast.func.obj.type, ClassType)
        file.write(f"meth_{ast.func.obj.type.name}_{ast.func.name}")
        args = [ast.func.obj] + ast.args
    else:
        _emit_expression(file, ast.func)
        args = ast.args

    file.write("(")
    _emit_commasep(file, args, (lambda arg: _emit_expression(file, arg)))
    file.write("))")


def _emit_expression(file: IO[str], ast: tast.Expression) -> None:
    if isinstance(ast, tast.IntConstant):
        file.write(f"((int64_t){ast.value}LL)")
    elif isinstance(ast, tast.ReturningCall):
        _emit_call(file, ast)
    elif isinstance(ast, tast.GetVar):
        file.write("var_" + ast.varname)
    elif isinstance(ast, tast.Constructor):
        file.write("ctor_" + ast.class_to_construct.name)
    elif isinstance(ast, tast.SetRef):
        file.write(f"({ast.refname} = ")
        _emit_expression(file, ast.value)
        file.write(")")
    elif isinstance(ast, tast.GetAttribute):
        file.write("((")
        _emit_expression(file, ast.obj)
        file.write(f")->memb_{ast.attribute})")
    elif isinstance(ast, tast.GetMethod):
        # This should return some kind of partial function, which isn't possible yet
        raise NotImplementedError
    else:
        raise NotImplementedError(ast)


def _emit_statement(file: IO[str], ast: tast.Statement) -> None:
    if isinstance(ast, tast.LetStatement):
        _emit_type(file, ast.value.type)
        file.write(f"var_{ast.varname} = ")
        _emit_expression(file, ast.value)
    elif isinstance(ast, (tast.ReturningCall, tast.VoidCall)):
        _emit_call(file, ast)
    elif isinstance(ast, tast.DecRefObject):
        file.write("decref(")
        _emit_expression(file, ast.value)
        file.write(")")
    elif isinstance(ast, tast.ReturnStatement):
        if ast.value is not None:
            file.write("retval = ")
            _emit_expression(file, ast.value)
            file.write(";")
            if ast.value.type.refcounted:
                file.write("incref(retval);")
        file.write("goto out")
    else:
        raise NotImplementedError(ast)
    file.write(";\n\t")


def _emit_type(file: IO[str], the_type: Optional[Type]) -> None:
    if the_type is INT:
        file.write("int64_t ")
    elif isinstance(the_type, ClassType):
        file.write(f"struct class_{the_type.name} *")
    elif the_type is None:
        file.write("void ")
    else:
        raise NotImplementedError(the_type)


def _emit_arg_def(file: IO[str], pair: Tuple[Type, str]) -> None:
    the_type, name = pair
    _emit_type(file, the_type)
    file.write("var_" + name)


def _emit_func_def(file: IO[str], funcdef: tast.FuncDef, c_name: str) -> None:
    _emit_type(file, funcdef.type.returntype)
    if funcdef.argnames:
        file.write(c_name)
        file.write("(")
        _emit_commasep(
            file,
            zip(funcdef.type.argtypes, funcdef.argnames),
            partial(_emit_arg_def, file),
        )
        file.write(")")
    else:
        file.write(c_name)
        file.write("(void)")

    file.write("{\n\t")
    if funcdef.type.returntype is not None:
        file.write("void *retval = NULL;\n\t")
    for refname, reftype in funcdef.refs:
        _emit_type(file, reftype)
        file.write(f"{refname} = NULL;\n\t")

    for statement in funcdef.body:
        _emit_statement(file, statement)

    # avoid problem with 'out:' being last thing in function
    file.write("out: (void)0;\n\t")
    for refname, reftype in reversed(funcdef.refs):
        file.write(f"if ({refname}) decref({refname});\n\t")
    if funcdef.type.returntype is not None:
        file.write("assert(retval); return retval;\n\t")
    file.write("\n}\n")


def emit_toplevel_statement(
    file: IO[str], top_statement: tast.ToplevelStatement
) -> None:
    if isinstance(top_statement, tast.FuncDef):
        _emit_func_def(file, top_statement, "var_" + top_statement.name)

    elif isinstance(top_statement, tast.ClassDef):
        # struct
        file.write("struct class_%s {\n" % top_statement.type.name)
        file.write("\tREFCOUNT_HEADER\n\t")
        for the_type, name in top_statement.type.members:
            _emit_type(file, the_type)
            file.write("memb_" + name + ";\n\t")
        file.write("\n};\n")

        # constructor
        _emit_type(file, top_statement.type)
        file.write(f"ctor_{top_statement.type.name}(")
        _emit_commasep(file, top_statement.type.members, partial(_emit_arg_def, file))
        file.write(") {\n\t")
        _emit_type(file, top_statement.type)
        file.write("obj = malloc(sizeof(*obj));\n")
        file.write("\tobj->refcount = 1;\n")
        for the_type, name in top_statement.type.members:
            file.write(f"\tobj->memb_{name} = var_{name};\n")
        file.write("\treturn obj;\n}\n")

        # methods
        for method in top_statement.body:
            _emit_func_def(
                file, method, f"meth_{top_statement.type.name}_{method.name}"
            )

    else:
        raise NotImplementedError(top_statement)
