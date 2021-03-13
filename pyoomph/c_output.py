from __future__ import annotations

import hashlib
import os
import pathlib
import re
from typing import Dict, List, Optional, TypeVar, Union

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
    return f"{name}: (void)0;\n"


class _FunctionEmitter:
    def __init__(self, file_pair: _FilePair) -> None:
        self.file_pair = file_pair
        self.session = file_pair.session  # TODO: get rid of this
        self.local_variable_names: Dict[ir.LocalVariable, str] = {}
        self.before_body = ""
        self.after_body = ""
        self.need_decref: List[ir.LocalVariable] = []
        self.varname_counter = 0

    def incref_var(self, var: ir.LocalVariable) -> str:
        return self.session.emit_incref(self.emit_var(var), var.type)

    def emit_call(
        self,
        func: str,
        args: List[ir.LocalVariable],
        result_var: Optional[ir.LocalVariable],
    ) -> str:
        args_string = ",".join(map(self.emit_var, args))
        if result_var is None:
            return f"{func}({args_string});\n"
        return f"{self.emit_var(result_var)} = {func}({args_string});\n"

    def emit_body(self, body: List[ir.Instruction]) -> str:
        return "\n\t".join(map(self.emit_instruction, body))

    def emit_instruction(self, ins: ir.Instruction) -> str:
        if isinstance(ins, ir.StringConstant):
            return f"{self.emit_var(ins.result)} = {self.file_pair.emit_string(ins.value)}; {self.incref_var(ins.result)};\n"

        if isinstance(ins, ir.IntConstant):
            return f"{self.emit_var(ins.result)} = {ins.value}LL;\n"

        if isinstance(ins, ir.FloatConstant):
            return f"{self.emit_var(ins.result)} = {ins.value};\n"

        if isinstance(ins, ir.VarCpy):
            return f"{self.emit_var(ins.dest)} = {self.emit_var(ins.source)};\n"

        if isinstance(ins, ir.IncRef):
            return self.incref_var(ins.var) + ";\n"

        if isinstance(ins, ir.DecRef):
            return (
                self.session.emit_decref(self.emit_var(ins.var), ins.var.type) + ";\n"
            )

        if isinstance(ins, ir.CallFunction):
            return self.emit_call(self.emit_var(ins.func), ins.args, ins.result)

        if isinstance(ins, ir.CallMethod):
            return self.emit_call(
                f"meth_{self.session.get_type_c_name(ins.obj.type)}_{ins.method_name}",
                [ins.obj] + ins.args,
                ins.result,
            )

        if isinstance(ins, ir.CallConstructor):
            return self.emit_call(
                "ctor_" + self.session.get_type_c_name(ins.result.type),
                ins.args,
                ins.result,
            )

        if isinstance(ins, ir.Return):
            if ins.value is not None:
                return f"{self.incref_var(ins.value)}; retval = {self.emit_var(ins.value)}; goto out;\n"
            return "goto out;\n"

        if isinstance(ins, ir.GetAttribute):
            return f"{self.emit_var(ins.result)} = {self.emit_var(ins.obj)}->memb_{ins.attribute};\n"

        if isinstance(ins, ir.SetAttribute):
            return f"{self.emit_var(ins.obj)}->memb_{ins.attribute} = {self.emit_var(ins.value)};\n"

        if isinstance(ins, ir.PointersEqual):
            return f"{self.emit_var(ins.result)} = ({self.emit_var(ins.lhs)} == {self.emit_var(ins.rhs)});\n"

        if isinstance(ins, ir.If):
            then = self.emit_body(ins.then)
            otherwise = self.emit_body(ins.otherwise)
            return f"""
            if ({self.emit_var(ins.condition)}) {{
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
                if (!{self.emit_var(ins.cond)})
                    break;
                {body}
                {_emit_label(ins.loop_id + "_continue")}
                {incr}
            }}
            {_emit_label(ins.loop_id + "_break")}
            """

        if isinstance(ins, ir.Continue):
            return f"goto {ins.loop_id}_continue;\n"

        if isinstance(ins, ir.Break):
            return f"goto {ins.loop_id}_break;\n"

        if isinstance(ins, ir.InstantiateUnion):
            assert isinstance(ins.result.type, ir.UnionType)
            assert ins.result.type.type_members is not None
            membernum = ins.result.type.type_members.index(ins.value.type)
            return "%s = (%s){ .val = { .item%d = %s }, .membernum = %d };\n" % (
                self.emit_var(ins.result),
                self.file_pair.emit_type(ins.result.type),
                membernum,
                self.emit_var(ins.value),
                membernum,
            )

        if isinstance(ins, ir.GetFromUnion):
            assert isinstance(ins.union.type, ir.UnionType)
            assert ins.union.type.type_members is not None
            membernum = ins.union.type.type_members.index(ins.result.type)
            return f"{self.emit_var(ins.result)} = {self.emit_var(ins.union)}.val.item{membernum};"

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
            switch ({self.emit_var(ins.union)}.membernum) {{
                {body_code}
                default:
                    assert(0);
            }}
            """

        if isinstance(ins, ir.IsNull):
            return f"{self.emit_var(ins.result)} = {self.emit_var(ins.var)}.isnull;\n"

        if isinstance(ins, ir.SetToNull):
            if isinstance(ins.var.type, UnionType):
                return f"{self.emit_var(ins.var)}.membernum = -1;\n"
            if (
                ins.var.type.generic_origin is not None
                and ins.var.type.generic_origin.generic is OPTIONAL
            ):
                c_type = self.file_pair.emit_type(ins.var.type)
                return f"{self.emit_var(ins.var)} = ({c_type}){{ .isnull = true }};\n"
            if not ins.var.type.refcounted:
                # Must not run for non-refcounted unions or optionals
                return ""
            return f"{self.emit_var(ins.var)} = NULL;\n"

        raise NotImplementedError(ins)

    def add_local_var(
        self, var: ir.LocalVariable, *, declare: bool = True, need_decref: bool = True
    ) -> None:
        assert var not in self.local_variable_names
        # Ensure different functions don't share variable names.
        # This makes grepping the C code easier.
        self.varname_counter += 1
        name = f"var{self.varname_counter}"
        self.local_variable_names[var] = name
        if declare:
            self.before_body += f"{self.file_pair.emit_type(var.type)} {name};\n"
            # TODO: add these in ast2ir?
            self.before_body += self.emit_instruction(ir.SetToNull(var))
        if need_decref:
            self.need_decref.append(var)

    def emit_var(self, var: ir.Variable) -> str:
        if not isinstance(var, ir.LocalVariable):
            return self.file_pair.emit_var(var)

        try:
            return self.local_variable_names[var]
        except KeyError:
            self.add_local_var(var)
            return self.local_variable_names[var]

    def emit_funcdef(
        self,
        funcdef: Union[ir.FuncDef, ir.MethodDef],
        c_name: str,
    ) -> None:
        for var in funcdef.argvars:
            self.add_local_var(var, declare=False, need_decref=False)

        body_instructions = self.emit_body(funcdef.body)
        decrefs = "".join(
            self.session.emit_decref(self.emit_var(var), var.type) + ";\n"
            for var in reversed(self.need_decref)
        )

        if isinstance(funcdef, ir.FuncDef):
            assert isinstance(funcdef.var.type, FunctionType)
            functype = funcdef.var.type
        else:
            functype = funcdef.type

        if functype.returntype is not None:
            self.before_body += (
                f"{self.file_pair.emit_type(functype.returntype)} retval;\n"
            )
            self.after_body += "return retval;\n"

        argnames = [self.emit_var(var) for var in funcdef.argvars]
        self.file_pair.define_function(
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
        "struct": """
        struct class_%(type_cname)s {
            bool isnull;
            %(itemtype)s value;
        };
        """,
        "function_decls": """
        struct class_%(type_cname)s ctor_%(type_cname)s(%(itemtype)s val);
        %(itemtype)s meth_%(type_cname)s_get(struct class_%(type_cname)s opt);
        struct class_Str *meth_%(type_cname)s_to_string(struct class_%(type_cname)s opt);
        """,
        "function_defs": """
        struct class_%(type_cname)s ctor_%(type_cname)s(%(itemtype)s val)
        {
            %(incref_val)s;
            return (struct class_%(type_cname)s) { false, val };
        }

        %(itemtype)s meth_%(type_cname)s_get(struct class_%(type_cname)s opt)
        {
            assert(!opt.isnull);
            %(itemtype)s val = opt.value;
            %(incref_val)s;
            return val;
        }

        struct class_Str *meth_%(type_cname)s_to_string(struct class_%(type_cname)s opt)
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
        "struct": """
        struct class_%(type_cname)s {
            REFCOUNT_HEADER
            int64_t len;
            int64_t alloc;
            %(itemtype)s smalldata[8];
            %(itemtype)s *data;
        };
        """,
        "function_decls": """
        struct class_%(type_cname)s *ctor_%(type_cname)s(void);
        void dtor_%(type_cname)s (void *ptr);
        void meth_%(type_cname)s_push(struct class_%(type_cname)s *self, %(itemtype)s val);
        void meth_%(type_cname)s_push_all(struct class_%(type_cname)s *self, const struct class_%(type_cname)s *src);
        %(itemtype)s meth_%(type_cname)s_pop(struct class_%(type_cname)s *self);
        %(itemtype)s meth_%(type_cname)s_get(struct class_%(type_cname)s *self, int64_t i);
        %(itemtype)s meth_%(type_cname)s_first(struct class_%(type_cname)s *self);
        %(itemtype)s meth_%(type_cname)s_last(struct class_%(type_cname)s *self);
        int64_t meth_%(type_cname)s_length(struct class_%(type_cname)s *self);
        struct class_Str *meth_%(type_cname)s_to_string(struct class_%(type_cname)s *self);
        struct class_%(type_cname)s *meth_%(type_cname)s_reversed(const struct class_%(type_cname)s *self);
        """,
        "function_defs": """
        struct class_%(type_cname)s *ctor_%(type_cname)s(void)
        {
            struct class_%(type_cname)s *res = malloc(sizeof(*res));
            assert(res);
            res->refcount = 1;
            res->len = 0;
            res->data = res->smalldata;
            res->alloc = sizeof(res->smalldata)/sizeof(res->smalldata[0]);
            return res;
        }

        void dtor_%(type_cname)s (void *ptr)
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

        void class_%(type_cname)s_ensure_alloc(struct class_%(type_cname)s *self, int64_t n)
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

        void meth_%(type_cname)s_push(struct class_%(type_cname)s *self, %(itemtype)s val)
        {
            class_%(type_cname)s_ensure_alloc(self, self->len + 1);
            self->data[self->len++] = val;
            %(incref_val)s;
        }

        void meth_%(type_cname)s_push_all(struct class_%(type_cname)s *self, const struct class_%(type_cname)s *src)
        {
            class_%(type_cname)s_ensure_alloc(self, self->len + src->len);
            memcpy(self->data + self->len, src->data, sizeof(src->data[0]) * src->len);
            for (int64_t i = 0; i < src->len; i++) {
                %(itemtype)s val = src->data[i];
                %(incref_val)s;
            }
            self->len += src->len;
        }

        %(itemtype)s meth_%(type_cname)s_pop(struct class_%(type_cname)s *self)
        {
            if (self->len == 0)
                panic_printf("pop from empty list");
            return self->data[--self->len];
        }

        %(itemtype)s meth_%(type_cname)s_get(struct class_%(type_cname)s *self, int64_t i)
        {
            if (i < 0)
                panic_printf("negative list index %%d", (long)i);
            if (i >= self->len)
                panic_printf("list index %%ld beyond end of list of length %%ld", (long)i, (long)self->len);

            %(itemtype)s val = self->data[i];
            %(incref_val)s;
            return val;
        }

        %(itemtype)s meth_%(type_cname)s_first(struct class_%(type_cname)s *self)
        {
            if (self->len == 0)
                panic_printf("can't get first item of empty list");
            %(itemtype)s val = self->data[0];
            %(incref_val)s;
            return val;
        }

        %(itemtype)s meth_%(type_cname)s_last(struct class_%(type_cname)s *self)
        {
            if (self->len == 0)
                panic_printf("can't get last item of empty list");
            %(itemtype)s val = self->data[self->len - 1];
            %(incref_val)s;
            return val;
        }

        int64_t meth_%(type_cname)s_length(struct class_%(type_cname)s *self)
        {
            return self->len;
        }

        // TODO: rewrite better in the language itself
        struct class_Str *meth_%(type_cname)s_to_string(struct class_%(type_cname)s *self)
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

        struct class_%(type_cname)s *meth_%(type_cname)s_reversed(const struct class_%(type_cname)s *self)
        {
            struct class_%(type_cname)s *res = ctor_%(type_cname)s();
            class_%(type_cname)s_ensure_alloc(res, self->len);
            for (int64_t i = 0; i < self->len; i++) {
                %(itemtype)s val = self->data[self->len - 1 - i];
                res->data[i] = val;
                %(incref_val)s;
            }
            res->len = self->len;
            return res;
        }
        """,
    },
}


# Represents .c and .h file, and possibly *the* type defined in those.
# That's right, each type goes to separate .c and .h file.
class _FilePair:
    def __init__(self, session: Session, source_path: pathlib.Path, pair_id: str):
        self.source_path = source_path
        self.id = pair_id  # used in file names and type names
        self.session = session
        self.variable_names: Dict[ir.Variable, str] = {
            ir.builtin_variables["__argv_count"]: "argv_count",
            ir.builtin_variables["__argv_get"]: "argv_get",
            ir.builtin_variables["__io_mkdir"]: "io_mkdir",
            ir.builtin_variables["__io_read_file"]: "io_read_file",
            ir.builtin_variables["__io_write_file"]: "io_write_file",
            ir.builtin_variables["__string_find_internal"]: "string_find_internal",
            ir.builtin_variables["__subprocess_run"]: "subprocess_run",
            ir.builtin_variables["assert"]: "oomph_assert",
            ir.builtin_variables["false"]: "false",
            ir.builtin_variables["print"]: "io_print",
            ir.builtin_variables["true"]: "true",
            **{var: name for name, var in ir.special_variables.items()},
        }
        self.strings: Dict[str, str] = {}
        self.struct = ""
        self.string_defs = ""
        self.function_decls = ""
        self.function_defs = ""
        self.includes: List[_FilePair] = []

    def emit_type(self, the_type: Optional[Type]) -> str:
        if the_type is None:
            return "void"
        if the_type is INT:
            return "int64_t"
        if the_type is FLOAT:
            return "double"
        if the_type is BOOL:
            return "bool"

        if the_type in builtin_types.values():
            type_id = the_type.name
        else:
            defining_file_pair = self.session.get_file_pair_for_type(the_type)
            if (
                defining_file_pair is not self
                and defining_file_pair not in self.includes
            ):
                self.includes.append(defining_file_pair)
            type_id = defining_file_pair.id

        if the_type.refcounted and not isinstance(the_type, UnionType):
            return f"struct class_{type_id} *"
        return f"struct class_{type_id}"

    def emit_method(self, the_type: Type, method_name: str) -> str:
        if the_type in builtin_types.values():
            return f"meth_{the_type.name}_{method_name}"

        defining_file_pair = self.session.get_file_pair_for_type(the_type)
        return f"meth_{defining_file_pair.id}_{method_name}"

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
        self.function_decls += declaration + ";\n"
        self.function_defs += declaration + "{" + body + "}"

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

    def emit_var(self, var: ir.Variable) -> str:
        assert not isinstance(var, ir.LocalVariable)  # TODO: is this correct?
        try:
            return self.variable_names[var]
        except KeyError:
            assert isinstance(var.type, FunctionType)
            if isinstance(var, ir.ExportVariable) and var.name == "main":
                c_name = "oomph_main"
            elif var.name in {
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
                "__Bool_to_string",
            }:
                # Class implemented in C, method implemented in builtins.oomph
                # TODO: check self.source_path
                c_name = "meth_" + var.name.lstrip("_")
            else:
                c_name = self.id + "_" + var.name

            self.variable_names[var] = c_name
            return c_name

    # Must not be called multiple times for the same _FilePair
    def define_type(self, the_type: Type) -> None:
        if the_type.generic_origin is not None:
            assert not self.struct
            itemtype = the_type.generic_origin.arg
            code_dict = _generic_c_codes[the_type.generic_origin.generic]
            string_formatting = {
                "type_cname": self.session.get_type_c_name(the_type),
                "itemtype": self.emit_type(itemtype),
                "itemtype_string": self.emit_string(itemtype.name),
                "itemtype_cname": self.session.get_type_c_name(itemtype),
                # TODO: replace with macros
                "incref_val": self.session.emit_incref("val", itemtype),
                "decref_val": self.session.emit_decref("val", itemtype),
            }
            self.struct = code_dict["struct"] % string_formatting
            self.function_decls += code_dict["function_decls"] % string_formatting
            self.function_defs += code_dict["function_defs"] % string_formatting

        elif isinstance(the_type, UnionType):
            raise NotImplementedError
        #            assert the_type.type_members is not None
        #
        #            to_string_cases = "".join(
        #                f"""
        #                case {num}:
        #                    valstr = meth_{self.session.get_type_c_name(typ)}_to_string(obj.val.item{num});
        #                    break;
        #                """
        #                for num, typ in enumerate(the_type.type_members)
        #            )
        #            self.function_decls += f"struct class_Str *meth_{self.id}_to_string(struct class_{self.id} obj);"
        #            self.function_defs += f"""
        #            struct class_Str *meth_{self.id}_to_string(struct class_{self.id} obj)
        #            {{
        #                struct class_Str *valstr;
        #                switch(obj.membernum) {{
        #                    {to_string_cases}
        #                    default:
        #                        assert(0);
        #                }}
        #
        #                struct class_Str *res = {self.emit_string(the_type.name)};
        #                string_concat_inplace(&res, "(");
        #                string_concat_inplace(&res, valstr->str);
        #                string_concat_inplace(&res, ")");
        #                decref(valstr, dtor_Str);
        #                return res;
        #            }}
        #            """
        #
        #            # To incref/decref unions, we need to know the value of membernum
        #            # and incref/decref the correct member of the union. This
        #            # union-specific function handles that.
        #            incref_cases = "".join(
        #                f"""
        #                case {num}:
        #                    {self.emit_incref(f"obj.val.item{num}", typ)};
        #                    break;
        #                """
        #                for num, typ in enumerate(the_type.type_members)
        #            )
        #            decref_cases = "".join(
        #                f"""
        #                case {num}:
        #                    {self.emit_decref(f"obj.val.item{num}", typ)};
        #                    break;
        #                """
        #                for num, typ in enumerate(the_type.type_members)
        #            )
        #
        #            self.function_decls += f"""
        #            void incref_{self.id}(struct class_{self.id} obj);
        #            void decref_{self.id}(struct class_{self.id} obj);
        #            """
        #            self.function_defs += f"""
        #            void incref_{self.id}(struct class_{self.id} obj) {{
        #                switch(obj.membernum) {{
        #                    {incref_cases}
        #                    default:
        #                        assert(0);
        #                }}
        #            }}
        #            void decref_{self.id}(struct class_{self.id} obj) {{
        #                switch(obj.membernum) {{
        #                    case -1:   // variable not in use
        #                        break;
        #                    {decref_cases}
        #                    default:
        #                        assert(0);
        #                }}
        #            }}
        #            """
        #
        #            union_members = "".join(
        #                f"\t{self.emit_type(the_type)} item{index};\n"
        #                for index, the_type in enumerate(the_type.type_members)
        #            )
        #            assert not self.struct
        #            self.struct = f"""
        #            struct class_{self.id} {{
        #                union {{
        #                    {union_members}
        #                }} val;
        #                short membernum;
        #            }};
        #            """
        else:
            struct_members = "".join(
                f"{self.emit_type(the_type)} memb_{name};\n"
                for the_type, name in the_type.members
            )
            constructor_args = ",".join(
                f"{self.emit_type(the_type)} arg_{name}"
                for the_type, name in the_type.members
            )
            member_assignments = "".join(
                f"obj->memb_{name} = arg_{name};\n"
                for the_type, name in the_type.members
            )
            member_increfs = "".join(
                self.session.emit_incref(f"arg_{name}", the_type) + ";\n"
                for the_type, name in the_type.members
            )
            member_decrefs = "".join(
                self.session.emit_decref(f"obj->memb_{nam}", typ) + ";\n"
                for typ, nam in the_type.members
            )

            assert not self.struct
            self.struct = f"""
            struct class_{self.id} {{
                REFCOUNT_HEADER
                {struct_members}
            }};
            """
            self.function_decls += f"""
            {self.emit_type(the_type)} ctor_{self.id}({constructor_args});
            void dtor_{self.id}(void *ptr);
            """
            self.function_defs += f"""
            {self.emit_type(the_type)} ctor_{self.id}({constructor_args})
            {{
                {self.emit_type(the_type)} obj = malloc(sizeof(*obj));
                assert(obj);
                obj->refcount = 1;
                {member_assignments}
                {member_increfs}
                return obj;
            }}

            void dtor_{self.id}(void *ptr)
            {{
                struct class_{self.id} *obj = ptr;
                {member_decrefs}
                free(obj);
            }}
            """

    def emit_toplevel_declaration(
        self, top_declaration: ir.ToplevelDeclaration
    ) -> None:
        if isinstance(top_declaration, ir.FuncDef):
            _FunctionEmitter(self).emit_funcdef(
                top_declaration, self.emit_var(top_declaration.var)
            )

        elif isinstance(top_declaration, ir.TypeDef):
            new_pair = _FilePair(
                self.session,
                self.source_path,
                self.id + "_" + top_declaration.type.name,
            )
            self.session.type_to_file_pair[top_declaration.type] = new_pair
            new_pair.define_type(top_declaration.type)

        elif isinstance(top_declaration, ir.MethodDef):
            clASS = top_declaration.type.argtypes[0]
            _FunctionEmitter(self.session.type_to_file_pair[clASS]).emit_funcdef(
                top_declaration,
                f"meth_{self.session.get_type_c_name(clASS)}_{top_declaration.name}",
            )

        else:
            raise NotImplementedError(top_declaration)


def _create_id(readable_part: str, identifying_part: str) -> str:
    # TODO: avoid long file names
    md5 = hashlib.md5(identifying_part.encode("utf-8")).hexdigest()
    return re.sub(r"[^A-Za-z0-9]", "_", readable_part) + "_" + md5[:10]


# This state is shared between different files
class Session:
    def __init__(self, compilation_dir: pathlib.Path) -> None:
        self.compilation_dir = compilation_dir
        self.type_to_file_pair: Dict[Type, _FilePair] = {}
        self.source_path_to_file_pair: Dict[pathlib.Path, _FilePair] = {}

    def get_c_paths(self) -> List[pathlib.Path]:
        return [
            self.compilation_dir / (pair.id + ".c")
            for pair in list(self.type_to_file_pair.values())
            + list(self.source_path_to_file_pair.values())
        ]

    def get_file_pair_for_type(self, the_type: Type) -> _FilePair:
        if the_type not in self.type_to_file_pair:
            assert the_type.definition_path is None
            pair = _FilePair(self, None, _create_id(the_type.name, the_type.name))
            self.type_to_file_pair[the_type] = pair
            pair.define_type(the_type)
        return self.type_to_file_pair[the_type]

    def get_type_c_name(self, the_type: Type) -> str:
        if the_type in builtin_types.values():
            return the_type.name
        return self.type_to_file_pair[the_type].id

    # May evaluate c_expression several times
    def emit_incref(self, c_expression: str, the_type: Type) -> str:
        if isinstance(the_type, UnionType):
            return f"incref_{self.get_type_c_name(the_type)}({c_expression})"
        if (
            the_type.generic_origin is not None
            and the_type.generic_origin.generic is OPTIONAL
        ):
            value_incref = self.emit_incref(
                f"({c_expression}).value", the_type.generic_origin.arg
            )
            return f"do{{ if(!({c_expression}).isnull) {value_incref}; }} while(0)"
        if the_type.refcounted:
            return f"incref({c_expression})"
        return "(void)0"

    def emit_decref(self, c_expression: str, the_type: Type) -> str:
        if isinstance(the_type, UnionType):
            return f"decref_{self.get_type_c_name(the_type)}({c_expression})"
        if (
            the_type.generic_origin is not None
            and the_type.generic_origin.generic is OPTIONAL
        ):
            value_decref = self.emit_decref(
                f"({c_expression}).value", the_type.generic_origin.arg
            )
            return f"(({c_expression}).isnull ? (void)0 : {value_decref})"
        if the_type.refcounted:
            return f"decref(({c_expression}), dtor_{self.get_type_c_name(the_type)})"
        return "(void)0"

    def create_c_code(
        self, top_decls: List[ir.ToplevelDeclaration], source_path: pathlib.Path
    ) -> None:
        pair = _FilePair(
            self,
            source_path,
            _create_id(
                source_path.stem,
                os.path.relpath(source_path, self.compilation_dir.parent),
            ),
        )
        self.source_path_to_file_pair[source_path] = pair
        for top_declaration in top_decls:
            pair.emit_toplevel_declaration(top_declaration)

    # TODO: don't keep stuff in memory so much
    def write_everything(self) -> None:
        for file_pair in list(self.type_to_file_pair.values()) + list(
            self.source_path_to_file_pair.values()
        ):
            c_path = self.compilation_dir / (file_pair.id + ".c")
            h_path = self.compilation_dir / (file_pair.id + ".h")

            includes = "#include <lib/oomph.h>\n" + "".join(
                f'#include "{pair.id}.h"\n' for pair in file_pair.includes
            )
            h_code = includes + file_pair.struct + file_pair.function_decls
            c_code = (
                f'#include "{file_pair.id}.h"\n'
                + file_pair.string_defs
                + file_pair.function_defs
            )

            header_guard = "HEADER_GUARD_" + file_pair.id
            c_path.write_text(c_code + "\n", encoding="utf-8")
            h_path.write_text(
                f"""
                // Source path: {file_pair.source_path}
                #ifndef {header_guard}
                #define {header_guard}
                {h_code}
                #endif
                """
                + "\n",
                encoding="utf-8",
            )
