from __future__ import annotations

import itertools
import re
from typing import Dict, List, Optional, TypeVar, Union

import more_itertools

import compiler.typed_ast as tast
from compiler.types import BOOL, FLOAT, INT, LIST, OPTIONAL, STRING, Type

_T = TypeVar("_T")
_varnames = (f"var{i}" for i in itertools.count())


class _FunctionEmitter:
    def __init__(self, file_emitter: _FileEmitter) -> None:
        self.file_emitter = file_emitter
        self.before_body = ""
        self.name_mapping: Dict[str, str] = {}  # values are names in c

    def declare_local_var(self, the_type: Type) -> str:
        name = next(_varnames)
        self.before_body += f"{self.file_emitter.emit_type(the_type)} {name};\n\t"
        return name

    def emit_call(self, ast: Union[tast.ReturningCall, tast.VoidCall]) -> str:
        if isinstance(ast.func, tast.GetMethod):
            args = [ast.func.obj] + ast.args
        else:
            args = ast.args

        if isinstance(ast.func, tast.GetMethod):
            func = f"meth_{self.file_emitter.get_type_c_name(ast.func.obj.type)}_{ast.func.name}"
        else:
            func = self.emit_expression(ast.func)

        # In C, argument order is not guaranteed, but evaluation of comma
        # expressions is guaranteed. Comma-expression-evaluate all arguments
        # and put them to temporary variables, then do the call with the
        # temporary variables as arguments.
        varnames = [self.declare_local_var(arg.type) for arg in args]
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
            return "ctor_" + self.file_emitter.get_type_c_name(ast.class_to_construct)
        if isinstance(ast, tast.SetRef):
            # Must evaluate expression before decref because expression might
            # depend on the old value
            var = self.declare_local_var(ast.value.type)
            value = self.emit_expression(ast.value)
            decref = self.file_emitter.emit_decref(ast.refname, ast.value.type)
            return f"({var} = {value}, {decref}, {ast.refname} = {var})"
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
            var = self.declare_local_var(ast.value.type)
            assert ast.varname not in self.name_mapping
            self.name_mapping[ast.varname] = var
            return f"{var} = {self.emit_expression(ast.value)};\n\t"

        if isinstance(ast, tast.SetLocalVar):
            return f"{self.name_mapping[ast.varname]} = {self.emit_expression(ast.value)};\n\t"

        if isinstance(ast, (tast.ReturningCall, tast.VoidCall)):
            return self.emit_call(ast) + ";\n\t"

        if isinstance(ast, tast.DecRef):
            var = self.declare_local_var(ast.value.type)
            return (
                self.file_emitter.emit_decref(
                    self.emit_expression(ast.value), ast.value.type
                )
                + ";\n\t"
            )

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
        c_argnames = more_itertools.take(len(funcdef.argnames), _varnames)
        self.name_mapping.update(zip(funcdef.argnames, c_argnames))

        body = (
            (
                ""
                if funcdef.type.returntype is None
                else f"{self.file_emitter.emit_type(funcdef.type.returntype)} retval;\n\t"
            )
            + "".join(
                f"{self.file_emitter.emit_type(reftype)} {refname} = NULL;\n\t"
                for refname, reftype in funcdef.refs
            )
            + "".join(self.emit_statement(statement) for statement in funcdef.body)
            + self.emit_label("out")
            + "".join(
                self.file_emitter.emit_decref(refname, reftype) + ";\n\t"
                for refname, reftype in reversed(funcdef.refs)
            )
            + ("" if funcdef.type.returntype is None else "return retval;\n\t")
        )
        return (
            f"{self.file_emitter.emit_type(funcdef.type.returntype)} {c_name}("
            + (
                ",".join(
                    self.file_emitter.emit_type(the_type) + " " + name
                    for the_type, name in zip(funcdef.type.argtypes, c_argnames)
                )
                or "void"
            )
            + ") {\n\t"
            + self.before_body
            + body
            + "\n}\n\n"
        )


def _format_byte(byte: int) -> str:
    return r"'\x%02x'" % byte


_generic_c_codes = {
    OPTIONAL: """
struct class_%(c_name)s {
    bool isnull;
    %(c_type)s value;
};

struct class_%(c_name)s ctor_%(c_name)s(%(c_type)s val)
{
    return (struct class_%(c_name)s) { false, val };
}

%(c_type)s meth_%(c_name)s_get(struct class_%(c_name)s opt)
{
    assert(!opt.isnull);
#if %(is_refcounted)s
    incref(opt.value);
#endif
    return opt.value;
}

bool meth_%(c_name)s_is_null(struct class_%(c_name)s opt)
{
    return opt.isnull;
}
""",
    LIST: """
// TODO: have this struct on stack when possible, same with strings
struct class_%(c_name)s {
    REFCOUNT_HEADER
    int64_t len;
    int64_t alloc;
    %(c_type)s smalldata[8];
    %(c_type)s *data;
};

struct class_%(c_name)s *ctor_%(c_name)s(void)
{
    struct class_%(c_name)s *res = malloc(sizeof(*res));
    assert(res);
    res->refcount = 1;
    res->len = 0;
    res->data = res->smalldata;
    res->alloc = sizeof(res->smalldata)/sizeof(res->smalldata[0]);
    return res;
}

void dtor_%(c_name)s (void *ptr)
{
    struct class_%(c_name)s *self = ptr;
#if %(is_refcounted)s
    for (int64_t i = 0; i < self->len; i++)
        decref(self->data[i]);
#endif
    if (self->data != self->smalldata)
        free(self->data);
    free(self);
}

void class_%(c_name)s_ensure_alloc(struct class_%(c_name)s *self, int64_t n)
{
    assert(n >= 0);
    if (self->alloc >= n)
        return;

    while (self->alloc < n)
        self->alloc *= 2;

    if (self->data == self->smalldata) {
        self->data = malloc(self->alloc * sizeof(self->data[0]));
        assert(self->data);
        memcpy(self->data, self->smalldata, sizeof self->smalldata);
    } else {
        self->data = realloc(self->data, self->alloc * sizeof(self->data[0]));
        assert(self->data);
    }
}

void meth_%(c_name)s_push(struct class_%(c_name)s *self, %(c_type)s val)
{
    class_%(c_name)s_ensure_alloc(self, self->len + 1);
    self->data[self->len++] = val;
#if %(is_refcounted)s
    incref(val);
#endif
}

%(c_type)s meth_%(c_name)s_get(struct class_%(c_name)s *self, int64_t i)
{
    assert(0 <= i && i < self->len);
#if %(is_refcounted)s
    incref(self->data[i]);
#endif
    return self->data[i];
}

int64_t meth_%(c_name)s_length(struct class_%(c_name)s *self)
{
    return self->len;
}
""",
}


class _FileEmitter:
    def __init__(self) -> None:
        self.strings: Dict[str, str] = {}
        self.beginning = '#include "lib/lib.h"\n\n'
        self.generic_type_names: Dict[Type, str] = {}

    def emit_decref(self, c_expression: str, the_type: Type) -> str:
        if the_type.refcounted:
            return f"decref({c_expression}, dtor_{self.get_type_c_name(the_type)})"
        return "(void)0"

    def get_type_c_name(self, the_type: Type) -> str:
        if the_type.generic_origin is None:
            return the_type.name

        try:
            return self.generic_type_names[the_type]
        except KeyError:
            c_name = f"{the_type.generic_origin.generic.name}_{self.get_type_c_name(the_type.generic_origin.arg)}"
            self.generic_type_names[the_type] = c_name
            self.beginning += _generic_c_codes[the_type.generic_origin.generic] % {
                "c_name": c_name,
                "c_type": self.emit_type(the_type.generic_origin.arg),
                "is_refcounted": "1" if the_type.generic_origin.arg.refcounted else "0",
            }
            self.beginning += "\n"
            return c_name

    def emit_type(self, the_type: Optional[Type]) -> str:
        if the_type is None:
            return "void"
        if the_type is INT:
            return "int64_t"
        if the_type is FLOAT:
            return "double"
        if the_type is BOOL:
            return "bool"
        if the_type.refcounted:
            return f"struct class_{self.get_type_c_name(the_type)} *"
        return f"struct class_{self.get_type_c_name(the_type)}"

    def emit_string(self, value: str) -> str:
        if value not in self.strings:
            self.strings[value] = (
                f"string{len(self.strings)}_" + re.sub(r"[^A-Za-z0-9]", "", value)[:30]
            )

            # String constants consist of int64_t refcount set to -1,
            # followed by utf8, followed by zero byte
            # TODO: is this cross-platform enough?
            struct_bytes = b"\xff" * 8 + value.encode("utf-8") + b"\0"
            self.beginning += (
                f"{self.emit_type(STRING)} {self.strings[value]} = (void*)(unsigned char[])"
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
                ("struct class_%s {\n" % self.get_type_c_name(top_statement.type))
                + "\tREFCOUNT_HEADER\n\t"
                + "".join(
                    f"{self.emit_type(the_type)} memb_{name};\n\t"
                    for the_type, name in top_statement.type.members
                )
                + "\n};\n\n"
                # constructor
                + f"{self.emit_type(top_statement.type)} ctor_{self.get_type_c_name(top_statement.type)}("
                + ",".join(
                    f"{self.emit_type(the_type)} var_{name}"
                    for the_type, name in top_statement.type.members
                )
                + ") {\n\t"
                + f"{self.emit_type(top_statement.type)} obj = malloc(sizeof(*obj));\n\t"
                + "obj->refcount = 1;\n\t"
                + "".join(
                    f"obj->memb_{name} = var_{name};"
                    + (f"incref(var_{name});" if the_type.refcounted else "")
                    + "\n\t"
                    for the_type, name in top_statement.type.members
                )
                + "return obj;\n}\n\n"
                # destructor
                + f"void dtor_{self.get_type_c_name(top_statement.type)}(void *ptr)"
                + "{"
                + f"\n\tstruct class_{self.get_type_c_name(top_statement.type)} *obj = ptr;\n\t"
                + "".join(
                    self.emit_decref(f"obj->memb_{nam}", typ) + ";\n\t"
                    for typ, nam in top_statement.type.members
                )
                + "free(obj);\n}\n\n"
                # methods
                + "".join(
                    _FunctionEmitter(self).emit_funcdef(
                        method,
                        f"meth_{self.get_type_c_name(top_statement.type)}_{method.name}",
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
