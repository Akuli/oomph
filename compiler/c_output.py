from __future__ import annotations

import re
import string
from typing import Dict, List, Optional, TypeVar, Union

import compiler.typed_ast as tast
from compiler.types import BOOL, FLOAT, INT, STRING, Type

_T = TypeVar("_T")


def _emit_type(the_type: Optional[Type]) -> str:
    if the_type is INT:
        return "int64_t"
    if the_type is FLOAT:
        return "double"
    if the_type is BOOL:
        return "bool"
    if the_type is None:
        return "void"
    return f"struct class_{the_type.name} *"


class _FunctionEmitter:
    def __init__(self, file_emitter: _FileEmitter) -> None:
        self.file_emitter = file_emitter
        self.before_body = ""
        self.name_mapping: Dict[str, str] = {}  # values are names in c
        self.varname_counter = 0

    def create_local_var(self, the_type: Type, name_hint: str) -> str:
        name = f"{name_hint}_{self.varname_counter}"
        self.varname_counter += 1
        self.before_body += f"{_emit_type(the_type)} {name};\n\t"
        return name

    def emit_call(self, ast: Union[tast.ReturningCall, tast.VoidCall]) -> str:
        if isinstance(ast.func, tast.GetMethod):
            args = [ast.func.obj] + ast.args
        else:
            args = ast.args

        if isinstance(ast.func, tast.GetMethod):
            func = f"meth_{ast.func.obj.type.name}_{ast.func.name}"
        else:
            func = self.emit_expression(ast.func)

        # In C, argument order is not guaranteed, but evaluation of comma
        # expressions is guaranteed. Comma-expression-evaluate all arguments
        # and put them to temporary variables, then do the call with the
        # temporary variables as arguments.
        varnames = [self.create_local_var(arg.type, "arg") for arg in args]

        return (
            "("
            + " ".join(
                f"{var} = ({self.emit_expression(arg)}),"
                for var, arg in zip(varnames, args)
            )
            + f"{func}({','.join(varnames)}))"
        )

    def emit_expression(self, ast: tast.Expression) -> str:
        if isinstance(ast, tast.StringConstant):
            return self.file_emitter.emit_string(ast.value)
        if isinstance(ast, tast.IntConstant):
            return f"((int64_t){ast.value}LL)"
        if isinstance(ast, tast.FloatConstant):
            return f"({ast.value})"
        if isinstance(ast, tast.ReturningCall):
            return self.emit_call(ast)
        if isinstance(ast, tast.GetVar):
            if ast.is_special:
                return ast.varname
            return self.name_mapping.get(ast.varname, f"var_{ast.varname}")
        if isinstance(ast, tast.Constructor):
            return "ctor_" + ast.class_to_construct.name
        if isinstance(ast, tast.SetRef):
            # Must evaluate expression before decref because expression might
            # depend on the old value
            var = self.create_local_var(ast.value.type, f'{ast.refname}_new')
            return f"({var} = {self.emit_expression(ast.value)}, decref({ast.refname}), {ast.refname} = {var})"
        if isinstance(ast, tast.GetAttribute):
            return f"(({self.emit_expression(ast.obj)})->memb_{ast.attribute})"
        if isinstance(ast, tast.GetMethod):
            # This should return some kind of partial function, which isn't possible yet
            raise NotImplementedError(
                "method objects without immediate calling don't work yet"
            )
        raise NotImplementedError(ast)

    def emit_label(self, name: str) -> str:
        # It's invalid c syntax to end a block with a label, (void)0 fixes
        return f"{name}: (void)0;\n\t"

    def emit_statement(self, ast: tast.Statement) -> str:
        if isinstance(ast, tast.CreateLocalVar):
            var = self.create_local_var(ast.value.type, ast.varname)
            assert ast.varname not in self.name_mapping
            self.name_mapping[ast.varname] = var
            return f"{var} = {self.emit_expression(ast.value)};\n\t"

        if isinstance(ast, tast.SetLocalVar):
            return f"{self.name_mapping[ast.varname]} = {self.emit_expression(ast.value)};\n\t"

        if isinstance(ast, (tast.ReturningCall, tast.VoidCall)):
            return self.emit_call(ast) + ";\n\t"

        if isinstance(ast, tast.DecRef):
            var = self.create_local_var(ast.value.type, "decreffing_var")
            return f"decref({self.emit_expression(ast.value)});\n\t"

        if isinstance(ast, tast.Return):
            if ast.value is not None and ast.value.type.refcounted:
                return f"retval = {self.emit_expression(ast.value)}; incref(retval); goto out;\n\t"
            if ast.value is not None:
                return f"retval = {self.emit_expression(ast.value)}; goto out;\n\t"
            return "goto out;\n\t"

        if isinstance(ast, tast.If):
            return (
                ("if (%s) {\n\t" % self.emit_expression(ast.condition))
                + "".join(self.emit_statement(s) for s in ast.then)
                + "} else {\n\t"
                + "".join(self.emit_statement(s) for s in ast.otherwise)
                + "}\n\t"
            )

        if isinstance(ast, tast.Loop):
            # Can't use C's for loop because it's limited to one statement
            return (
                "".join(self.emit_statement(s) for s in ast.init)
                + ("while (%s) {\n\t" % self.emit_expression(ast.cond))
                + "".join(self.emit_statement(s) for s in ast.body)
                + self.emit_label(ast.loop_id)
                + "".join(self.emit_statement(s) for s in ast.incr)
                + "}\n\t"
            )

        if isinstance(ast, tast.Continue):
            # Can't use C's continue because continue must emit_funcdef condition
            return f"goto {ast.loop_id};\n\t"

        if isinstance(ast, tast.Break):
            return "break;\n\t"

        raise NotImplementedError(ast)

    def emit_funcdef(self, funcdef: tast.FuncDef, c_name: str) -> str:
        body = (
            (
                ""
                if funcdef.type.returntype is None
                else f"{_emit_type(funcdef.type.returntype)} retval;\n\t"
            )
            + "".join(
                f"{_emit_type(reftype)} {refname} = NULL;\n\t"
                for refname, reftype in funcdef.refs
            )
            + "".join(self.emit_statement(statement) for statement in funcdef.body)
            + self.emit_label("out")
            + "".join(
                f"decref({refname});\n\t" for refname, reftype in reversed(funcdef.refs)
            )
            + ("" if funcdef.type.returntype is None else "return retval;\n\t")
        )
        return (
            f"\n{_emit_type(funcdef.type.returntype)} {c_name}("
            + (
                ",".join(
                    f"{_emit_type(the_type)} var_{name}"
                    for the_type, name in zip(funcdef.type.argtypes, funcdef.argnames)
                )
                or "void"
            )
            + ") {\n\t"
            + self.before_body
            + body
            + "\n}\n"
        )


def _format_byte(byte: int) -> str:
    return r"'\x%02x'" % byte


class _FileEmitter:
    def __init__(self) -> None:
        self.strings: Dict[str, str] = {}
        self.beginning = '#include "lib/lib.h"\n\n'

    def emit_string(self, value: str) -> str:
        if value not in self.strings:
            self.strings[value] = (
                f"string{len(self.strings)}_" + re.sub(r"[^A-Za-z0-9]", "", value)[:10]
            )

            # String constants consist of int64_t refcount set to -1,
            # followed by utf8, followed by zero byte
            # TODO: is this cross-platform enough?
            struct_bytes = b"\xff" * 8 + value.encode("utf-8") + b"\0"
            self.beginning += (
                f"{_emit_type(STRING)} {self.strings[value]} = (void*)(unsigned char[])"
                + "{"
                + ", ".join(map(_format_byte, struct_bytes))
                + "};\n"
            )
        return self.strings[value]

    def emit_toplevel_statement(self, top_statement: tast.ToplevelStatement) -> str:
        if isinstance(top_statement, tast.FuncDef):
            return _FunctionEmitter(self).emit_funcdef(
                top_statement, "var_" + top_statement.name
            )

        if isinstance(top_statement, tast.ClassDef):
            return (
                # struct
                ("struct class_%s {\n" % top_statement.type.name)
                + "\tREFCOUNT_HEADER\n\t"
                + "".join(
                    f"{_emit_type(the_type)} memb_{name};\n\t"
                    for the_type, name in top_statement.type.members
                )
                + "\n};\n"
                # constructor
                + f"{_emit_type(top_statement.type)} ctor_{top_statement.type.name}("
                + ",".join(
                    f"{_emit_type(the_type)} var_{name}"
                    for the_type, name in top_statement.type.members
                )
                + ") {\n\t"
                + f"{_emit_type(top_statement.type)} obj = malloc(sizeof(*obj));\n\t"
                + "obj->refcount = 1;\n\t"
                + "".join(
                    f"obj->memb_{name} = var_{name};\n\t"
                    for the_type, name in top_statement.type.members
                )
                + "return obj;\n}\n"
                # methods
                + "".join(
                    _FunctionEmitter(self).emit_funcdef(
                        method, f"meth_{top_statement.type.name}_{method.name}"
                    )
                    for method in top_statement.body
                )
            )

        raise NotImplementedError(top_statement)


def run(ast: List[tast.ToplevelStatement]) -> str:
    emitter = _FileEmitter()
    code = "".join(
        emitter.emit_toplevel_statement(top_statement) for top_statement in ast
    )
    return emitter.beginning + code
