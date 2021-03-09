from __future__ import annotations

import hashlib
import pathlib
import re
from typing import Dict, List, Optional, Tuple, TypeVar, Union

from pyoomph import ir
from pyoomph.types import (
    BOOL,
    FLOAT,
    INT,
    LIST,
    OPTIONAL,
    STRING,
    FunctionType,
    Type,
    UnionType,
    builtin_types,
)

_T = TypeVar("_T")


def _emit_label(name: str) -> str:
    # It's invalid c syntax to end a block with a label, (void)0 fixes
    return f"{name}: (void)0;"


class _FunctionEmitter:
    def __init__(self, file_emitter: _FileEmitter) -> None:
        self.file_emitter = file_emitter
        self.variable_names = self.file_emitter.variable_names.copy()
        self.before_body = ""
        self.after_body = ""
        self.need_decref: List[ir.LocalVariable] = []

    def incref_var(self, var: ir.LocalVariable) -> str:
        return self.file_emitter.emit_incref(self.variable_names[var], var.type)

    def emit_call(
        self,
        func: str,
        args: List[ir.LocalVariable],
        result_var: Optional[ir.LocalVariable],
    ) -> str:
        args_string = ",".join(map(self.emit_local_var, args))
        if result_var is None:
            return f"{func}({args_string});"
        return f"{self.emit_local_var(result_var)} = {func}({args_string});"

    def emit_body(self, body: List[ir.Instruction]) -> str:
        return "\n\t".join(map(self.emit_instruction, body))

    def emit_instruction(self, ins: ir.Instruction) -> str:
        if isinstance(ins, ir.StringConstant):
            return f"{self.emit_local_var(ins.result)} = {self.file_emitter.emit_string(ins.value)}; {self.incref_var(ins.result)};"

        if isinstance(ins, ir.IntConstant):
            return f"{self.emit_local_var(ins.result)} = {ins.value}LL;"

        if isinstance(ins, ir.FloatConstant):
            return f"{self.emit_local_var(ins.result)} = {ins.value};"

        if isinstance(ins, ir.VarCpy):
            return (
                f"{self.emit_local_var(ins.dest)} = {self.variable_names[ins.source]};"
            )

        if isinstance(ins, ir.IncRef):
            return self.incref_var(ins.var) + ";"

        if isinstance(ins, ir.DecRef):
            return (
                self.file_emitter.emit_decref(
                    self.emit_local_var(ins.var), ins.var.type
                )
                + ";"
            )

        if isinstance(ins, ir.CallFunction):
            return self.emit_call(self.variable_names[ins.func], ins.args, ins.result)

        if isinstance(ins, ir.CallMethod):
            return self.emit_call(
                f"meth_{self.file_emitter.get_type_c_name(ins.obj.type)}_{ins.method_name}",
                [ins.obj] + ins.args,
                ins.result,
            )

        if isinstance(ins, ir.CallConstructor):
            return self.emit_call(
                "ctor_" + self.file_emitter.get_type_c_name(ins.result.type),
                ins.args,
                ins.result,
            )

        if isinstance(ins, ir.Return):
            if ins.value is not None:
                return f"{self.incref_var(ins.value)}; retval = {self.emit_local_var(ins.value)}; goto out;"
            return "goto out;"

        if isinstance(ins, ir.GetAttribute):
            return f"{self.emit_local_var(ins.result)} = {self.emit_local_var(ins.obj)}->memb_{ins.attribute}; {self.incref_var(ins.result)};"

        if isinstance(ins, ir.PointersEqual):
            return f"{self.emit_local_var(ins.result)} = ({self.emit_local_var(ins.lhs)} == {self.emit_local_var(ins.rhs)});"

        if isinstance(ins, ir.If):
            then = self.emit_body(ins.then)
            otherwise = self.emit_body(ins.otherwise)
            return f"""
            if ({self.emit_local_var(ins.condition)}) {{
                {then}
            }} else {{
                {otherwise}
            }}
            """

        if isinstance(ins, ir.Loop):
            cond_code = self.emit_body(ins.cond_code)
            body = self.emit_body(ins.body)
            incr = self.emit_body(ins.incr)
            return f"""
            while(1) {{
                {cond_code}
                if (!{self.emit_local_var(ins.cond)})
                    break;
                {body}
                {_emit_label(ins.loop_id)}  // oomph 'continue' jumps here
                {incr}
            }}
            """

        if isinstance(ins, ir.Continue):
            # Can't use C's continue because continue must emit_funcdef condition
            return f"goto {ins.loop_id};"

        if isinstance(ins, ir.Break):
            return "break;"

        if isinstance(ins, ir.InstantiateUnion):
            assert isinstance(ins.result.type, ir.UnionType)
            assert ins.result.type.type_members is not None
            membernum = ins.result.type.type_members.index(ins.value.type)
            return "%s = (%s){ .val = { .item%d = %s }, .membernum = %d };" % (
                self.emit_local_var(ins.result),
                self.file_emitter.emit_type(ins.result.type),
                membernum,
                self.emit_local_var(ins.value),
                membernum,
            )

        if isinstance(ins, ir.Null):
            return self.emit_local_var(ins.result) + ".isnull = true;"

        if isinstance(ins, ir.GetFromUnion):
            assert isinstance(ins.union.type, ir.UnionType)
            assert ins.union.type.type_members is not None
            membernum = ins.union.type.type_members.index(ins.result.type)
            return f"{self.emit_local_var(ins.result)} = {self.emit_local_var(ins.union)}.val.item{membernum};"

        if isinstance(ins, ir.Switch):
            assert isinstance(ins.union.type, ir.UnionType)
            assert ins.union.type.type_members is not None

            body_code = ""
            for membernum, the_type in enumerate(ins.union.type.type_members):
                case_content = self.emit_body(ins.cases[the_type])
                body_code += f"""
                case {membernum}:
                    {case_content}
                    break;
                """

            return f"""
            switch ({self.emit_local_var(ins.union)}.membernum) {{
                {body_code}
                default:
                    assert(0);
            }}
            """
        raise NotImplementedError(ins)

    def add_local_var(
        self, var: ir.LocalVariable, *, declare: bool = True, need_decref: bool = True
    ) -> None:
        assert var not in self.variable_names
        # Ensure different functions don't share variable names.
        # This makes grepping the C code easier.
        name = self.file_emitter.get_var_name()
        self.variable_names[var] = name
        if declare:
            self.before_body += f"{self.file_emitter.emit_type(var.type)} {name}"
            if var.type.refcounted:
                if isinstance(var.type, UnionType):
                    self.before_body += "= { .membernum = -1 }"
                elif var.type.generic_origin is not None and var.type.generic_origin.generic is OPTIONAL:
                    self.before_body += "= { .isnull = true }"
                else:
                    self.before_body += "= NULL"
            self.before_body += ";\n"
        if need_decref:
            self.need_decref.append(var)

    def emit_local_var(self, var: ir.LocalVariable) -> str:
        try:
            return self.variable_names[var]
        except KeyError:
            self.add_local_var(var)
            return self.variable_names[var]

    def emit_funcdef(
        self,
        funcdef: Union[ir.FuncDef, ir.MethodDef],
        c_name: str,
    ) -> None:
        for var in funcdef.argvars:
            self.add_local_var(var, declare=False, need_decref=False)

        body_instructions = self.emit_body(funcdef.body)
        decrefs = "".join(
            self.file_emitter.emit_decref(self.variable_names[var], var.type) + ";"
            for var in reversed(self.need_decref)
        )

        if isinstance(funcdef, ir.FuncDef):
            assert isinstance(funcdef.var.type, FunctionType)
            functype = funcdef.var.type
        else:
            functype = funcdef.type

        if functype.returntype is not None:
            self.before_body += (
                f"{self.file_emitter.emit_type(functype.returntype)} retval;"
            )
            self.after_body += "return retval;"

        argnames = [self.variable_names[var] for var in funcdef.argvars]
        self.file_emitter.define_function(
            c_name,
            functype,
            argnames,
            (
                self.before_body
                + body_instructions
                + _emit_label("out")
                + decrefs
                + self.after_body
            ),
        )


_generic_c_codes = {
    OPTIONAL: {
        "structs": """
        struct class_%(type_cname)s {
            bool isnull;
            %(itemtype)s value;
        };
        """,
        "function_decls": """
        static struct class_%(type_cname)s ctor_%(type_cname)s(%(itemtype)s val);
        static %(itemtype)s meth_%(type_cname)s_get(struct class_%(type_cname)s opt);
        static bool meth_%(type_cname)s_is_null(struct class_%(type_cname)s opt);
        static struct class_Str *meth_%(type_cname)s_to_string(struct class_%(type_cname)s opt);
        """,
        "function_defs": """
        static struct class_%(type_cname)s ctor_%(type_cname)s(%(itemtype)s val)
        {
            %(incref_val)s;
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
    },
    LIST: {
        # TODO: have this struct on stack when possible, same with strings
        "structs": """
        struct class_%(type_cname)s {
            REFCOUNT_HEADER
            int64_t len;
            int64_t alloc;
            %(itemtype)s smalldata[8];
            %(itemtype)s *data;
        };
        """,
        "function_decls": """
        static struct class_%(type_cname)s *ctor_%(type_cname)s(void);
        static void dtor_%(type_cname)s (void *ptr);
        static void meth_%(type_cname)s_push(struct class_%(type_cname)s *self, %(itemtype)s val);
        static void meth_%(type_cname)s_push_all(struct class_%(type_cname)s *self, const struct class_%(type_cname)s *src);
        static %(itemtype)s meth_%(type_cname)s_get(struct class_%(type_cname)s *self, int64_t i);
        static int64_t meth_%(type_cname)s_length(struct class_%(type_cname)s *self);
        static struct class_Str *meth_%(type_cname)s_to_string(struct class_%(type_cname)s *self);
        """,
        "function_defs": """
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

        static void meth_%(type_cname)s_push_all(struct class_%(type_cname)s *self, const struct class_%(type_cname)s *src)
        {
            class_%(type_cname)s_ensure_alloc(self, self->len + src->len);
            memcpy(self->data + self->len, src->data, sizeof(src->data[0]) * src->len);
            for (int64_t i = 0; i < src->len; i++) {
                %(itemtype)s val = src->data[i];
                %(incref_val)s;
            }
            self->len += src->len;
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
    },
}


class _FileEmitter:
    def __init__(
        self,
        session: Session,
        path: pathlib.Path,
    ):
        self.path = path
        self.session = session
        self.varname_counter = 0
        self.variable_names: Dict[ir.Variable, str] = {
            ir.builtin_variables["__argv_count"]: "argv_count",
            ir.builtin_variables["__argv_get"]: "argv_get",
            ir.builtin_variables["__io_mkdir"]: "io_mkdir",
            ir.builtin_variables["__io_read_file"]: "io_read_file",
            ir.builtin_variables["__io_write_file"]: "io_write_file",
            ir.builtin_variables["__string_find_first_internal"]: "string_find_first_internal",
            ir.builtin_variables["__subprocess_run"]: "subprocess_run",
            ir.builtin_variables["assert"]: "oomph_assert",
            ir.builtin_variables["false"]: "false",
            ir.builtin_variables["print"]: "io_print",
            ir.builtin_variables["true"]: "true",
            **{
                exp.value: name
                for exp, name in self.session.export_c_names.items()
                if isinstance(exp.value, ir.ExportVariable)
            },
            **{var: name for name, var in ir.special_variables.items()},
        }
        self.generic_type_names: Dict[Type, str] = {}
        self.strings: Dict[str, str] = {}

        self.union_decls = ""
        self.structs = ""
        self.function_decls = ""
        self.function_defs = ""
        self.string_defs = ""

    def _get_exportable_name(self, namespace: pathlib.Path, name: str) -> str:
        # FIXME: this may collide if there is foo/lol.oomph and bar/lol.oomph
        return "oomph_" + re.sub(r"[^A-Za-z_]", "", namespace.stem) + "_" + name

    def define_function(
        self, function_name: str, the_type: FunctionType, argnames: List[str], body: str
    ) -> None:
        assert len(the_type.argtypes) == len(argnames)
        arg_decls = [
            self.emit_type(argtype) + " " + name
            for argtype, name in zip(the_type.argtypes, argnames)
        ]

        declaration = "%s %s(%s)" % (
            self.emit_type(the_type.returntype),
            function_name,
            (", ".join(arg_decls) or "void"),
        )
        self.function_decls += declaration + ";"
        self.function_defs += declaration + "{" + body + "}"

    def get_var_name(self) -> str:
        self.varname_counter += 1
        return f"var{self.varname_counter}"

    def emit_incref(self, c_expression: str, the_type: Type) -> str:
        if isinstance(the_type, UnionType):
            return f"incref(({c_expression}).val.item0)"
        if the_type.generic_origin is not None and the_type.generic_origin.generic is OPTIONAL:
            value_incref = self.emit_incref(f'({c_expression}).value', the_type.generic_origin.arg)
            return f'(({c_expression}).isnull ? (void)0 : {value_incref})'
        if the_type.refcounted:
            return f"incref({c_expression})"
        return "(void)0"

    def emit_decref(self, c_expression: str, the_type: Type) -> str:
        if isinstance(the_type, UnionType):
            return f"decref_{self.get_type_c_name(the_type)}(({c_expression}))"
        if the_type.generic_origin is not None and the_type.generic_origin.generic is OPTIONAL:
            value_decref = self.emit_decref(f'({c_expression}).value', the_type.generic_origin.arg)
            return f'(({c_expression}).isnull ? (void)0 : {value_decref})'
        if the_type.refcounted:
            return f"decref(({c_expression}), dtor_{self.get_type_c_name(the_type)})"
        return "(void)0"

    def get_type_c_name(self, the_type: Type) -> str:
        if the_type.generic_origin is None:
            if the_type in builtin_types.values():
                return the_type.name
            assert the_type.definition_path is not None, the_type
            return self._get_exportable_name(the_type.definition_path, the_type.name)

        try:
            return self.generic_type_names[the_type]
        except KeyError:
            itemtype = the_type.generic_origin.arg
            type_cname = f"{the_type.generic_origin.generic.name}_{self.get_type_c_name(itemtype)}"
            self.generic_type_names[the_type] = type_cname

            code_dict = _generic_c_codes[the_type.generic_origin.generic]
            substitutions = {
                "type_cname": type_cname,
                "itemtype": self.emit_type(itemtype),
                "itemtype_cname": self.get_type_c_name(itemtype),
                "itemtype_string": the_type.name,
                "incref_val": self.emit_incref("val", itemtype),
                "decref_val": self.emit_decref("val", itemtype),
            }
            self.structs += f"""
            #ifndef {type_cname}_DEFINED
            #define {type_cname}_DEFINED
            {code_dict["structs"] % substitutions}
            #endif
            """
            self.function_decls += code_dict["function_decls"] % substitutions
            self.function_defs += code_dict["function_defs"] % substitutions
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
        if the_type.refcounted and not isinstance(the_type, UnionType) and (
            the_type.generic_origin is None or the_type.generic_origin.generic is not OPTIONAL):
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

            array_content = ", ".join(r"'\x%02x'" % byte for byte in struct_bytes)
            self.string_defs += f"""
            static {self.emit_type(STRING)} {self.strings[value]}
            = (void*)(unsigned char[]){{ {array_content} }};
            """
        return self.strings[value]

    def emit_toplevel_declaration(
        self, top_declaration: ir.ToplevelDeclaration
    ) -> None:
        if isinstance(top_declaration, ir.FuncDef):
            assert top_declaration.var not in self.variable_names
            if (
                isinstance(top_declaration.var, ir.ExportVariable)
                and top_declaration.var.name == "main"
            ):
                c_name = "oomph_main"
            elif top_declaration.var.name in {
                "__List_Str_join",
                "__Str_center_pad",
                "__Str_contains",
                "__Str_count",
                "__Str_ends_with",
                "__Str_find_first",
                "__Str_left_pad",
                "__Str_left_trim",
                "__Str_repeat",
                "__Str_replace",
                "__Str_right_pad",
                "__Str_right_trim",
                "__Str_split",
                "__Str_starts_with",
                "__Str_trim",
                "__bool_to_string",
            }:
                # Class implemented in C, method implemented in builtins.oomph
                c_name = "meth_" + top_declaration.var.name.lstrip("_")
            else:
                c_name = self._get_exportable_name(self.path, top_declaration.var.name)

            assert top_declaration.var not in self.variable_names
            assert top_declaration.var not in self.session.export_c_names

            self.variable_names[top_declaration.var] = c_name
            if isinstance(top_declaration.var, ir.ExportVariable):
                [export] = [
                    exp
                    for exp in self.session.exports
                    if exp.value is top_declaration.var
                ]
                self.session.export_c_names[export] = c_name

            _FunctionEmitter(self).emit_funcdef(
                top_declaration,
                self.variable_names[top_declaration.var],
            )

        elif isinstance(top_declaration, ir.ClassDef):
            struct_members = "".join(
                f"{self.emit_type(the_type)} memb_{name};\n\t"
                for the_type, name in top_declaration.type.members
            )
            constructor_args = ",".join(
                f"{self.emit_type(the_type)} arg_{name}"
                for the_type, name in top_declaration.type.members
            )
            member_assignments = "".join(
                f"obj->memb_{name} = arg_{name};\n"
                for the_type, name in top_declaration.type.members
            )
            member_increfs = "".join(
                self.emit_incref(f"arg_{name}", the_type) + ";\n"
                for the_type, name in top_declaration.type.members
            )
            member_decrefs = "".join(
                self.emit_decref(f"obj->memb_{nam}", typ) + ";\n"
                for typ, nam in top_declaration.type.members
            )
            for method in top_declaration.body:
                _FunctionEmitter(self).emit_funcdef(
                    method,
                    f"meth_{self.get_type_c_name(top_declaration.type)}_{method.name}",
                )

            c_name = self.get_type_c_name(top_declaration.type)
            if top_declaration.export:
                [export] = [
                    exp
                    for exp in self.session.exports
                    if exp.value is top_declaration.type
                ]
                self.session.export_c_names[export] = c_name

            self.structs += f"""
            struct class_{c_name} {{
                REFCOUNT_HEADER
                {struct_members}
            }};
            """
            self.function_decls += f"""
            {self.emit_type(top_declaration.type)} ctor_{c_name}({constructor_args});
            void dtor_{c_name}(void *ptr);
            """
            self.function_defs += f"""
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
            """

        elif isinstance(top_declaration, ir.UnionDef):
            assert top_declaration.type.type_members is not None
            c_name = self.get_type_c_name(top_declaration.type)

            # to_string method
            to_string_cases = "".join(
                f"""
                case {num}:
                    valstr = meth_{self.get_type_c_name(typ)}_to_string(obj.val.item{num});
                    break;
                """
                for num, typ in enumerate(top_declaration.type.type_members)
            )
            self.function_decls += (
                f"struct class_Str *meth_{c_name}_to_string(struct class_{c_name} obj);"
            )
            self.function_defs += f"""
            struct class_Str *meth_{c_name}_to_string(struct class_{c_name} obj)
            {{
                struct class_Str *valstr;
                switch(obj.membernum) {{
                    {to_string_cases}
                    default:
                        assert(0);
                }}

                struct class_Str *res = {self.emit_string("union " + top_declaration.type.name)};
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
                    {self.emit_decref(f"obj.val.item{num}", typ)};
                    break;
                """
                for num, typ in enumerate(top_declaration.type.type_members)
            )
            self.function_decls += f"void decref_{c_name}(struct class_{c_name} obj);"
            self.function_defs += f"""
            void decref_{c_name}(struct class_{c_name} obj) {{
                switch(obj.membernum) {{
                    case -1:   // variable not in use
                        break;
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
            self.structs += f"""
            struct class_{c_name} {{
                union {{
                    {union_members}
                }} val;
                short membernum;
            }};
            """

        else:
            raise NotImplementedError(top_declaration)


class Session:
    def __init__(self) -> None:
        # This state is shared between different files
        self.exports: List[ir.Export] = []
        self.export_c_names: Dict[ir.Export, str] = {}

    def create_c_code(
        self,
        ast: List[ir.ToplevelDeclaration],
        path: pathlib.Path,
        include_list: List[str],
    ) -> Tuple[str, str]:
        includes = "#include <lib/oomph.h>\n" + "".join(
            f'#include "{header}"\n' for header in include_list
        )

        emitter = _FileEmitter(self, path)
        for top_declaration in ast:
            emitter.emit_toplevel_declaration(top_declaration)

        h_code = includes + emitter.structs + emitter.function_decls
        c_code = h_code + emitter.string_defs + emitter.function_defs
        header_guard = "HEADER_" + hashlib.md5(c_code.encode("utf-8")).hexdigest()
        return (
            c_code,
            f"""
            #ifndef {header_guard}
            #define {header_guard}
            {h_code}
            #endif""",
        )
