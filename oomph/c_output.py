from __future__ import annotations

import hashlib
import pathlib
import re
from typing import Dict, List, Optional, Tuple, TypeVar, Union

import oomph.typed_ast as tast
from oomph.types import (
    BOOL,
    FLOAT,
    INT,
    LIST,
    OPTIONAL,
    STRING,
    FunctionType,
    Type,
    UnionType,
)

_T = TypeVar("_T")


class _FunctionEmitter:
    def __init__(self, file_emitter: _FileEmitter) -> None:
        self.file_emitter = file_emitter
        self.variable_names = self.file_emitter.variable_names.copy()
        self.before_body = ""
        self.after_body = ""

    def add_local_var(self, var: tast.LocalVariable, *, declare: bool = True) -> None:
        # Ensure different functions don't share variable names.
        # This makes grepping the C code easier.
        name = self.file_emitter.get_var_name()
        assert var not in self.variable_names
        self.variable_names[var] = name
        if declare:
            self.before_body += f"{self.file_emitter.emit_type(var.type)} {name};\n\t"

    def create_local_var(self, the_type: Type) -> tast.LocalVariable:
        var = tast.LocalVariable("c_output_var", the_type)
        self.add_local_var(var)
        return var

    def emit_call(self, ast: Union[tast.ReturningCall, tast.VoidCall]) -> str:
        if isinstance(ast.func, tast.GetMethod):
            args = [ast.func.obj] + ast.args
            func = f"meth_{self.file_emitter.get_type_c_name(ast.func.obj.type)}_{ast.func.name}"
        elif (
            isinstance(ast.func, tast.GetVar)
            and ast.func.var is tast.builtin_variables["assert"]
        ):
            assert ast.func.lineno is not None, ast.func
            args = ast.args + [tast.IntConstant(ast.func.lineno)]
            func = self.emit_expression(ast.func)
        else:
            args = ast.args
            func = self.emit_expression(ast.func)

        # In C, argument order is not guaranteed, but evaluation of comma
        # expressions is guaranteed. Comma-expression-evaluate all arguments
        # and put them to temporary variables, then do the call with the
        # temporary variables as arguments.
        temp_vars = [self.create_local_var(arg.type) for arg in args]
        comma_exprs = " ".join(
            f"{self.variable_names[var]} = ({self.emit_expression(arg)}),"
            for var, arg in zip(temp_vars, args)
        )
        return f"( {comma_exprs} {func} ({','.join(self.variable_names[v] for v in  temp_vars)}) )"

    def emit_expression(self, ast: tast.Expression) -> str:
        if isinstance(ast, tast.StringConstant):
            return self.file_emitter.emit_string(ast.value)
        if isinstance(ast, tast.IntConstant):
            return f"((int64_t){ast.value}LL)"
        if isinstance(ast, tast.FloatConstant):
            return f"({ast.value})"
        if isinstance(ast, tast.ReturningCall):
            return self.emit_call(ast)
        if isinstance(ast, tast.BoolAnd):
            return (
                f"({self.emit_expression(ast.lhs)} && {self.emit_expression(ast.rhs)})"
            )
        if isinstance(ast, tast.BoolOr):
            return (
                f"({self.emit_expression(ast.lhs)} || {self.emit_expression(ast.rhs)})"
            )
        if isinstance(ast, tast.Null):
            return "((" + self.file_emitter.emit_type(ast.type) + "){.isnull=true})"
        if isinstance(ast, tast.GetVar):
            return self.variable_names[ast.var]
        if isinstance(ast, tast.Constructor):
            return "ctor_" + self.file_emitter.get_type_c_name(ast.class_to_construct)
        if isinstance(ast, tast.SetRef):
            # Must evaluate expression before decref because expression might
            # depend on the old value
            var = self.create_local_var(ast.value.type)
            value = self.emit_expression(ast.value)
            decref = self.file_emitter.emit_decref(
                ast.refname, ast.value.type, semicolon=False
            )
            return f""" (
            {self.variable_names[var]} = {value},
            {decref},
            {ast.refname} = {self.variable_names[var]} ) """
        if isinstance(ast, tast.GetAttribute):
            return f"(({self.emit_expression(ast.obj)})->memb_{ast.attribute})"
        if isinstance(ast, tast.GetMethod):
            # This should return some kind of partial function
            raise NotImplementedError(
                "method objects without immediate calling don't work yet"
            )
        if isinstance(ast, tast.InstantiateUnion):
            assert ast.type.type_members is not None
            membernum = ast.type.type_members.index(ast.value.type)
            return "((%s){ .val = { .item%d = %s }, .membernum = %d })" % (
                self.file_emitter.emit_type(ast.type),
                membernum,
                self.emit_expression(ast.value),
                membernum,
            )
        if isinstance(ast, tast.StatementAndExpression):
            statement = self.emit_statement(ast.statement).rstrip().rstrip(";")
            expression = self.emit_expression(ast.expression)
            return f"(({statement}), ({expression}))"
        raise NotImplementedError(ast)

    def emit_label(self, name: str) -> str:
        # It's invalid c syntax to end a block with a label, (void)0 fixes
        return f"{name}: (void)0;\n\t"

    def emit_statement(self, ast: tast.Statement) -> str:
        if isinstance(ast, tast.CreateLocalVar):
            self.add_local_var(ast.var)
            return f"{self.variable_names[ast.var]} = {self.emit_expression(ast.value)};\n\t"

        if isinstance(ast, tast.SetLocalVar):
            return f"{self.variable_names[ast.var]} = {self.emit_expression(ast.value)};\n\t"

        if isinstance(ast, (tast.ReturningCall, tast.VoidCall)):
            return self.emit_call(ast) + ";\n\t"

        if isinstance(ast, tast.DecRef):
            return self.file_emitter.emit_decref(
                self.emit_expression(ast.value), ast.value.type
            )

        if isinstance(ast, tast.Return):
            if ast.value is not None:
                return f"""
                retval = {self.emit_expression(ast.value)};
                {self.file_emitter.emit_incref("retval", ast.value.type)}
                goto out;
                """
            return "goto out;"

        if isinstance(ast, tast.If):
            return f"""
            if ({self.emit_expression(ast.condition)}) {{
                {"".join(self.emit_statement(s) for s in ast.then)}
            }} else {{
                {"".join(self.emit_statement(s) for s in ast.otherwise)}
            }}
            """

        if isinstance(ast, tast.Loop):
            # While loop because I couldn't get C's for loop to work here
            return f"""
            {"".join(self.emit_statement(s) for s in ast.init)}
            while ({self.emit_expression(ast.cond)}) {{
                {"".join(self.emit_statement(s) for s in ast.body)}
                {self.emit_label(ast.loop_id)}  // oomph 'continue' jumps here
                {"".join(self.emit_statement(s) for s in ast.incr)}
            }}
            """

        if isinstance(ast, tast.Continue):
            # Can't use C's continue because continue must emit_funcdef condition
            return f"goto {ast.loop_id};"

        if isinstance(ast, tast.Break):
            return "break;"

        if isinstance(ast, tast.Switch):
            assert isinstance(ast.union.type, UnionType)
            assert ast.union.type.type_members is not None

            union_var = self.create_local_var(ast.union.type)
            body_code = ""
            for membernum, the_type in enumerate(ast.union.type.type_members):
                [(specific_var, body)] = [
                    (var, body)
                    for var, body in ast.cases.items()
                    if var.type is the_type
                ]
                self.add_local_var(specific_var)
                case_content = "".join(self.emit_statement(s) for s in body)
                body_code += f"""
                case {membernum}:
                    {self.variable_names[specific_var]} = {self.variable_names[union_var]}.val.item{membernum};
                    {case_content}
                    break;
                """

            return f"""
            {self.variable_names[union_var]} = {self.emit_expression(ast.union)};
            switch ({self.variable_names[union_var]}.membernum) {{
                {body_code}
                default:
                    assert(0);
            }}
            """

        raise NotImplementedError(ast)

    def emit_funcdef(
        self,
        funcdef: Union[tast.FuncDef, tast.MethodDef],
        c_name: str,
        *,
        static: bool = True,
    ) -> str:
        for var in funcdef.argvars:
            self.add_local_var(var, declare=False)

        ref_declarations = "".join(
            "%s %s = %s;\n\t"
            % (
                self.file_emitter.emit_type(reftype),
                refname,
                "{0}" if isinstance(reftype, UnionType) else "NULL",
            )
            for refname, reftype in funcdef.refs
        )
        decrefs = "".join(
            self.file_emitter.emit_decref(refname, reftype)
            for refname, reftype in reversed(funcdef.refs)
        )
        body_statements = "".join(self.emit_statement(s) for s in funcdef.body)

        if isinstance(funcdef, tast.FuncDef):
            assert isinstance(funcdef.var.type, FunctionType)
            functype = funcdef.var.type
        else:
            functype = funcdef.type

        if functype.returntype is not None:
            self.before_body += (
                f"{self.file_emitter.emit_type(functype.returntype)} retval;"
            )
            self.after_body += "return retval;"

        varnames = [self.variable_names[var] for var in funcdef.argvars]

        if not static:
            self.file_emitter.h_code += (
                self.file_emitter.declare_function(c_name, functype, static=False)
                + ";\n"
            )

        return f"""
        {self.file_emitter.declare_function(c_name, functype, varnames, static)}
        {{
            {self.before_body}
            {ref_declarations}
            {body_statements}

        {self.emit_label("out")}
            {decrefs}
            {self.after_body}
        }}
        """


def _format_byte(byte: int) -> str:
    return r"'\x%02x'" % byte


_generic_c_codes = {
    OPTIONAL: (
        """
        struct class_%(type_cname)s {
            bool isnull;
            %(itemtype)s value;
        };
        static struct class_%(type_cname)s ctor_%(type_cname)s(%(itemtype)s val);
        static %(itemtype)s meth_%(type_cname)s_get(struct class_%(type_cname)s opt);
        static bool meth_%(type_cname)s_is_null(struct class_%(type_cname)s opt);
        static struct class_Str *meth_%(type_cname)s_to_string(struct class_%(type_cname)s opt);
        """,
        """
        static struct class_%(type_cname)s ctor_%(type_cname)s(%(itemtype)s val)
        {
            return (struct class_%(type_cname)s) { false, val };
        }

        static %(itemtype)s meth_%(type_cname)s_get(struct class_%(type_cname)s opt)
        {
            assert(!opt.isnull);
            %(itemtype)s val = opt.value;
            %(incref_val)s;
            return val;
        }

        static bool meth_%(type_cname)s_is_null(struct class_%(type_cname)s opt)
        {
            return opt.isnull;
        }

        static struct class_Str *meth_%(type_cname)s_to_string(struct class_%(type_cname)s opt)
        {
            if (opt.isnull)
                return cstr_to_string("null");

            struct class_Str *res = cstr_to_string("%(itemtype_string)s(");  // TODO: escaping?
            struct class_Str *s = meth_%(itemtype_cname)s_to_string(opt.value);
            string_concat_inplace(&res, s->str);
            decref(s, dtor_Str);
            string_concat_inplace(&res, ")");
            return res;
        }
        """,
    ),
    LIST: (
        """
        // TODO: have this struct on stack when possible, same with strings
        struct class_%(type_cname)s {
            REFCOUNT_HEADER
            int64_t len;
            int64_t alloc;
            %(itemtype)s smalldata[8];
            %(itemtype)s *data;
        };

        static struct class_%(type_cname)s *ctor_%(type_cname)s(void);
        static void dtor_%(type_cname)s (void *ptr);
        static void meth_%(type_cname)s_push(struct class_%(type_cname)s *self, %(itemtype)s val);
        static %(itemtype)s meth_%(type_cname)s_get(struct class_%(type_cname)s *self, int64_t i);
        static int64_t meth_%(type_cname)s_length(struct class_%(type_cname)s *self);
        static struct class_Str *meth_%(type_cname)s_to_string(struct class_%(type_cname)s *self);
        """,
        """
        static struct class_%(type_cname)s *ctor_%(type_cname)s(void)
        {
            struct class_%(type_cname)s *res = malloc(sizeof(*res));
            assert(res);
            res->refcount = 1;
            res->len = 0;
            res->data = res->smalldata;
            res->alloc = sizeof(res->smalldata)/sizeof(res->smalldata[0]);
            return res;
        }

        static void dtor_%(type_cname)s (void *ptr)
        {
            struct class_%(type_cname)s *self = ptr;
            for (int64_t i = 0; i < self->len; i++) {
                %(itemtype)s val = self->data[i];
                %(decref_val)s;
            }
            if (self->data != self->smalldata)
                free(self->data);
            free(self);
        }

        static void class_%(type_cname)s_ensure_alloc(struct class_%(type_cname)s *self, int64_t n)
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

        static void meth_%(type_cname)s_push(struct class_%(type_cname)s *self, %(itemtype)s val)
        {
            class_%(type_cname)s_ensure_alloc(self, self->len + 1);
            self->data[self->len++] = val;
            %(incref_val)s;
        }

        static %(itemtype)s meth_%(type_cname)s_get(struct class_%(type_cname)s *self, int64_t i)
        {
            assert(0 <= i && i < self->len);
            %(itemtype)s val = self->data[i];
            %(incref_val)s;
            return val;
        }

        static int64_t meth_%(type_cname)s_length(struct class_%(type_cname)s *self)
        {
            return self->len;
        }

        // TODO: rewrite better in the language itself
        static struct class_Str *meth_%(type_cname)s_to_string(struct class_%(type_cname)s *self)
        {
            struct class_Str *res = cstr_to_string("[");

            for (int64_t i = 0; i < self->len; i++) {
                if (i != 0) {
                    string_concat_inplace(&res, ", ");
                }
                struct class_Str *s = meth_%(itemtype_cname)s_to_string(self->data[i]);
                string_concat_inplace(&res, s->str);
                decref(s, dtor_Str);
            }

            string_concat_inplace(&res, "]");
            return res;
        }
        """,
    ),
}


class _FileEmitter:
    def __init__(
        self,
        path: pathlib.Path,
        exports: List[tast.Export],
        export_c_names: Dict[tast.Export, str],
        includes: List[str],
    ):
        self.path = path
        self.exports = exports
        self.export_c_names = export_c_names
        self.varname_counter = 0
        self.variable_names: Dict[tast.Variable, str] = {
            tast.builtin_variables["__io_mkdir"]: "io_mkdir",
            tast.builtin_variables["__io_read_file"]: "io_read_file",
            tast.builtin_variables["__io_write_file"]: "io_write_file",
            tast.builtin_variables["__subprocess_run"]: "subprocess_run",
            tast.builtin_variables["assert"]: "oomph_assert",
            tast.builtin_variables["false"]: "false",
            tast.builtin_variables["print"]: "io_print",
            tast.builtin_variables["true"]: "true",
            # https://github.com/python/mypy/issues/10171
            **export_var_names,  # type: ignore
            **{var: name for name, var in tast.special_variables.items()},
        }
        self.generic_type_names: Dict[Type, str] = {}
        self.strings: Dict[str, str] = {}

        self.h_code = "#include <lib/oomph.h>\n" + "".join(
            f'#include "{header}"\n' for header in includes
        )
        self.beginning = ""
        self.ending = ""

    def declare_function(
        self,
        function_name: str,
        the_type: FunctionType,
        argnames: Optional[List[str]] = None,
        static: bool = True,
    ) -> str:
        if argnames is None:
            arg_decls = [self.emit_type(argtype) for argtype in the_type.argtypes]
        else:
            assert len(the_type.argtypes) == len(argnames)
            arg_decls = [
                self.emit_type(argtype) + " " + name
                for argtype, name in zip(the_type.argtypes, argnames)
            ]

        return "%s %s %s(%s)" % (
            ("static" if static else ""),
            self.emit_type(the_type.returntype),
            function_name,
            (", ".join(arg_decls) or "void"),
        )

    def get_var_name(self) -> str:
        self.varname_counter += 1
        return f"var{self.varname_counter}"

    def emit_incref(
        self, c_expression: str, the_type: Type, *, semicolon: bool = True
    ) -> str:
        if the_type.refcounted:
            # Every member of the union is a pointer to a struct starting with
            # REFCOUNT_HEADER, so it doesn't matter which member is used.
            access = ".val.item0" if isinstance(the_type, UnionType) else ""
            result = f"incref(({c_expression}) {access})"
        else:
            result = "(void)0"
        return f"{result};\n\t" if semicolon else result

    def emit_decref(
        self, c_expression: str, the_type: Type, *, semicolon: bool = True
    ) -> str:
        if isinstance(the_type, UnionType):
            result = f"decref_{self.get_type_c_name(the_type)}(({c_expression}))"
        elif the_type.refcounted:
            result = f"decref(({c_expression}), dtor_{self.get_type_c_name(the_type)})"
        else:
            result = "(void)0"
        return f"{result};\n\t" if semicolon else result

    def get_type_c_name(self, the_type: Type) -> str:
        if the_type.generic_origin is None:
            return the_type.name

        try:
            return self.generic_type_names[the_type]
        except KeyError:
            itemtype = the_type.generic_origin.arg
            type_cname = f"{the_type.generic_origin.generic.name}_{self.get_type_c_name(itemtype)}"
            self.generic_type_names[the_type] = type_cname

            # TODO: use c code and h code separately
            c_code, h_code = _generic_c_codes[the_type.generic_origin.generic]
            self.beginning += (c_code + h_code) % {
                "type_cname": type_cname,
                "itemtype": self.emit_type(itemtype),
                "itemtype_cname": self.get_type_c_name(itemtype),
                "itemtype_string": the_type.name,
                "incref_val": self.emit_incref("val", itemtype, semicolon=False),
                "decref_val": self.emit_decref("val", itemtype, semicolon=False),
            }
            self.beginning += "\n"
            return type_cname

    def emit_type(self, the_type: Optional[Type]) -> str:
        if the_type is None:
            return "void"
        if the_type is INT:
            return "int64_t"
        if the_type is FLOAT:
            return "double"
        if the_type is BOOL:
            return "bool"
        if the_type.refcounted and not isinstance(the_type, UnionType):
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

            array_content = ", ".join(map(_format_byte, struct_bytes))
            self.beginning += f"""
            static {self.emit_type(STRING)} {self.strings[value]}
            = (void*)(unsigned char[]){{ {array_content} }};
            """
        return self.strings[value]

    def emit_toplevel_declaration(
        self, top_declaration: tast.ToplevelDeclaration
    ) -> str:
        if isinstance(top_declaration, tast.FuncDef):
            assert top_declaration.var not in self.variable_names
            if isinstance(top_declaration.var, tast.ExportVariable):
                if top_declaration.var.name == "main":
                    c_name = "oomph_main"
                else:
                    c_name = "export_" + self.path.stem + "_" + top_declaration.var.name
                    while c_name in self.export_c_names.values():
                        c_name += "_"
            else:
                c_name = "func_" + top_declaration.var.name

            assert top_declaration.var not in self.variable_names
            assert top_declaration.var not in self.export_c_names

            self.variable_names[top_declaration.var] = c_name
            if isinstance(top_declaration.var, tast.ExportVariable):
                [export] = [
                    exp for exp in self.exports if exp.value is top_declaration.var
                ]
                self.export_c_names[export] = c_name

            return _FunctionEmitter(self).emit_funcdef(
                top_declaration,
                self.variable_names[top_declaration.var],
                static=(not isinstance(top_declaration.var, tast.ExportVariable)),
            )

        if isinstance(top_declaration, tast.ClassDef):
            struct_members = "".join(
                f"{self.emit_type(the_type)} memb_{name};\n\t"
                for the_type, name in top_declaration.type.members
            )
            constructor_args = ",".join(
                f"{self.emit_type(the_type)} arg_{name}"
                for the_type, name in top_declaration.type.members
            )
            member_assignments = "".join(
                f"obj->memb_{name} = arg_{name};"
                for the_type, name in top_declaration.type.members
            )
            member_increfs = "".join(
                self.emit_incref(f"arg_{name}", the_type)
                for the_type, name in top_declaration.type.members
            )
            member_decrefs = "".join(
                self.emit_decref(f"obj->memb_{nam}", typ)
                for typ, nam in top_declaration.type.members
            )
            methods = "".join(
                _FunctionEmitter(self).emit_funcdef(
                    method,
                    f"meth_{self.get_type_c_name(top_declaration.type)}_{method.name}",
                    static=False,
                )
                for method in top_declaration.body
            )

            c_name = self.get_type_c_name(top_declaration.type)
            if top_declaration.export:
                [export] = [
                    exp for exp in self.exports if exp.value is top_declaration.type
                ]
                self.export_c_names[export] = c_name
            return f"""
            struct class_{c_name} {{
                REFCOUNT_HEADER
                {struct_members}
            }};

            {self.emit_type(top_declaration.type)} ctor_{c_name}({constructor_args})
            {{
                {self.emit_type(top_declaration.type)} obj = malloc(sizeof(*obj));
                assert(obj);
                obj->refcount = 1;
                {member_assignments}
                {member_increfs}
                return obj;
            }}

            void dtor_{c_name}(void *ptr)
            {{
                struct class_{c_name} *obj = ptr;
                {member_decrefs}
                free(obj);
            }}

            {methods}
            """

        if isinstance(top_declaration, tast.UnionDef):
            assert top_declaration.type.type_members is not None
            name = self.get_type_c_name(top_declaration.type)

            # to_string method
            to_string_cases = "".join(
                f"""
                case {num}:
                    valstr = meth_{self.get_type_c_name(typ)}_to_string(obj.val.item{num});
                    break;
                """
                for num, typ in enumerate(top_declaration.type.type_members)
            )
            self.ending += f"""
            struct class_Str *meth_{name}_to_string(struct class_{name} obj)
            {{
                struct class_Str *valstr;
                switch(obj.membernum) {{
                    {to_string_cases}
                    default:
                        assert(0);
                }}

                // TODO: escaping?
                struct class_Str *res = cstr_to_string("union {top_declaration.type.name}");
                string_concat_inplace(&res, "(");
                string_concat_inplace(&res, valstr->str);
                string_concat_inplace(&res, ")");
                decref(valstr, dtor_Str);
                return res;
            }}
            """

            # To decref unions, we need to know the value of membernum and
            # decref the correct member of the union. This union-specific
            # function handles that.
            decref_cases = "".join(
                f"""
                case {num}:
                    {self.emit_decref(f"obj.val.item{num}", typ)}
                    break;
                """
                for num, typ in enumerate(top_declaration.type.type_members)
            )
            self.ending += f"""
            void decref_{name}(struct class_{name} obj) {{
                switch(obj.membernum) {{
                    {decref_cases}
                    default:
                        assert(0);
                }}
            }}
            """

            union_members = "".join(
                f"\t{self.emit_type(the_type)} item{index};\n"
                for index, the_type in enumerate(top_declaration.type.type_members)
            )
            return f"""
            struct class_{name} {{
                union {{
                    {union_members}
                }} val;
                short membernum;
            }};

            // Forward decls of self.ending stuff
            struct class_Str *meth_{name}_to_string(struct class_{name} obj);
            void decref_{name}(struct class_{name} obj);
            """

        raise NotImplementedError(top_declaration)


def run(
    ast: List[tast.ToplevelDeclaration],
    path: pathlib.Path,
    exports: List[tast.Export],
    export_c_names: Dict[tast.Export, str],
    includes: List[str],
) -> Tuple[str, str]:
    emitter = _FileEmitter(path, export_c_names, includes)
    code = "".join(
        emitter.emit_toplevel_declaration(top_declaration) for top_declaration in ast
    )
    c_code = emitter.h_code + emitter.beginning + code + emitter.ending
    header_guard = "HEADER_" + hashlib.md5(c_code.encode("utf-8")).hexdigest()
    return (
        c_code,
        f"""
        #ifndef {header_guard}
        #define {header_guard}
        {emitter.h_code}
        #endif""",
    )
