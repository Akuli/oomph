from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Union

from pyoomph import ir
from pyoomph.types import (
    BOOL,
    FLOAT,
    INT,
    LIST,
    MAPPING,
    MAPPING_ITEM,
    NULL_TYPE,
    STRING,
    AutoType,
    FunctionType,
    Type,
    UnionType,
    builtin_types,
)


def _emit_label(name: str) -> str:
    # It's invalid c syntax to end a block with a label, (void)0 fixes
    return f"{name}: (void)0;\n"


def _create_id(readable_part: str, identifying_part: str) -> str:
    md5 = hashlib.md5(identifying_part.encode("utf-8")).hexdigest()
    return re.sub(r"[^A-Za-z0-9]", "_", readable_part) + "_" + md5[:10]


def _is_pointer(the_type: Type) -> bool:
    return (
        the_type.refcounted
        and not isinstance(the_type, UnionType)
        and the_type != STRING
        and (
            the_type.generic_origin is None
            or the_type.generic_origin.generic is not MAPPING_ITEM
        )
    )


# Sometimes C functions need to be converted to structs that have function and
# data. This allows passing around data with a function.
class _FuncStructWrapper:
    def __init__(self, file_pair: "_FilePair"):
        self._file_pair = file_pair
        self._wrapped_c_func_names: Set[str] = set()
        self._decreffer_names: Dict[Type, str] = {}

    # When a function wrapped in a struct is called, the first arg is the data,
    # even if it's not used. So we need to make new functions that ignore the
    # first argument.
    def wrap_function(self, c_name: str, functype: FunctionType) -> str:
        if c_name not in self._wrapped_c_func_names:
            argnames = [f"arg{i}" for i in range(len(functype.argtypes))]
            argdefs = ["void *data"] + [
                self._file_pair.emit_type(argtype) + " " + name
                for argtype, name in zip(functype.argtypes, argnames)
            ]
            return_if_needed = "" if functype.returntype is None else "return"

            self._file_pair.function_defs += f"""
            static {self._file_pair.emit_type(functype.returntype)}
            {c_name}_wrapper({','.join(argdefs)})
            {{
                {return_if_needed} {c_name}({','.join(argnames)});
            }}
            """
            self._wrapped_c_func_names.add(c_name)

        return c_name + "_wrapper"

    # When the function is destroyed, it doesn't know what type the data is,
    # but instead it has a list of functions and corresponding args to run.
    # To make that work, the compiler needs to create functions that do the
    # decreffing.
    def create_decreffer(self, the_type: Type) -> str:
        if the_type not in self._decreffer_names:
            name = f"decreffer{len(self._decreffer_names)}"
            self._decreffer_names[the_type] = name

            self._file_pair.function_defs += f"""
            static void {name}(void *ptr)
            {{
                {self._file_pair.emit_type(the_type)} obj = ptr;
                {self._file_pair.session.emit_decref('obj', the_type)};
            }}
            """
        return self._decreffer_names[the_type]


class _FunctionEmitter:
    def __init__(self, file_pair: _FilePair) -> None:
        self.file_pair = file_pair
        self.session = file_pair.session
        self.local_variable_names: Dict[ir.LocalVariable, str] = {}
        self.label_names: Dict[ir.GotoLabel, str] = {}
        self.before_body = ""
        self.after_body = ""
        self.need_decref: List[ir.LocalVariable] = []
        self.name_counter = 0

    def incref_var(self, var: ir.LocalVariable) -> str:
        return self.session.emit_incref(self.emit_var(var), var.type)

    def emit_call(
        self,
        func: str,
        args: List[ir.LocalVariable],
        result_var: Optional[ir.LocalVariable],
        *,
        wrapped_in_struct: bool = False,
    ) -> str:
        arg_strings = [self.emit_var(v) for v in args]
        if wrapped_in_struct:
            arg_strings.insert(0, func + "->data")
            func = func + "->func"

        call = func + "(" + ",".join(arg_strings) + ")"
        if result_var is None:
            return f"{call};\n"
        return f"{self.emit_var(result_var)} = {call};\n"

    def emit_body(self, body: List[ir.Instruction]) -> str:
        return "".join(map(self.emit_instruction, body))

    def _wrap_function_in_struct(
        self,
        functype: ir.FunctionType,
        c_funcname: str,
        result_varname: str,
        *,
        data_var: Optional[ir.LocalVariable] = None,
    ) -> str:
        wrapper = self.file_pair.func_struct_wrapper
        if data_var is None:
            cblist_length = 1  # NULL terminator
            wrapped = wrapper.wrap_function(c_funcname, functype)
            assigning_code = f"{result_varname}->func = {wrapped};\n"
        else:
            cblist_length = 2
            assert _is_pointer(data_var.type)  # TODO
            returntype = self.file_pair.emit_type(functype.returntype)
            assigning_code = f"""
            {result_varname}->data = {self.emit_var(data_var)};
            {self.incref_var(data_var)};

            // Need to cast because first argument differs (void pointer vs non-void pointer)
            {result_varname}->func = ({returntype}(*)()) {c_funcname};

            {result_varname}->cblist[0] = (struct DestroyCallback){{
                .func = {wrapper.create_decreffer(data_var.type)},
                .arg = {result_varname}->data,
            }};
            """

        # full struct needed for sizeof
        self.file_pair.emit_type(functype, can_fwd_declare_in_header=False)

        return f"""
        {result_varname} = calloc(1, sizeof(*{result_varname}) + {cblist_length}*sizeof({result_varname}->cblist[0]));
        assert({result_varname});
        // Should incref soon, no need to set nonzero refcount
        {assigning_code}
        """

    def emit_instruction(self, ins: ir.Instruction) -> str:
        if isinstance(ins, ir.StringConstant):
            return f"""
            {self.emit_var(ins.var)} = {self.file_pair.emit_string(ins.value)};
            {self.incref_var(ins.var)};
            """

        if isinstance(ins, ir.IntConstant):
            return f"{self.emit_var(ins.var)} = {ins.value}LL;\n"

        if isinstance(ins, ir.FloatConstant):
            return f"{self.emit_var(ins.var)} = {ins.value};\n"

        if isinstance(ins, ir.VarCpy):
            if isinstance(ins.dest.type, FunctionType) and not isinstance(
                ins.source, ir.LocalVariable
            ):
                return self._wrap_function_in_struct(
                    ins.dest.type, self.emit_var(ins.source), self.emit_var(ins.dest)
                )
            return f"{self.emit_var(ins.dest)} = {self.emit_var(ins.source)};\n"

        if isinstance(ins, ir.IncRef):
            return self.incref_var(ins.var) + ";\n"

        if isinstance(ins, ir.DecRef):
            return (
                self.session.emit_decref(self.emit_var(ins.var), ins.var.type) + ";\n"
            )

        if isinstance(ins, ir.CallFunction):
            return self.emit_call(
                self.emit_var(ins.func),
                ins.args,
                ins.result,
                wrapped_in_struct=isinstance(ins.func, ir.LocalVariable),
            )

        if isinstance(ins, ir.CallMethod):
            return self.emit_call(
                f"meth_{self.session.get_type_c_name(ins.obj.type)}_{ins.method_name}",
                [ins.obj] + ins.args,
                ins.result,
            )

        if isinstance(ins, ir.GetMethod):
            functype = ins.method_var.type
            assert isinstance(functype, FunctionType)

            # TODO: support non-pointer types
            return self._wrap_function_in_struct(
                functype,
                f"meth_{self.session.get_type_c_name(ins.obj.type)}_{ins.method}",
                self.emit_var(ins.method_var),
                data_var=ins.obj,
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

        if isinstance(ins, (ir.SetAttribute, ir.GetAttribute)):
            op = "->" if _is_pointer(ins.obj.type) else "."
            var = self.emit_var(ins.attribute_var)
            attrib = self.emit_var(ins.obj) + op + "memb_" + ins.attribute

            return (
                f"{attrib} = {var};\n"
                if isinstance(ins, ir.SetAttribute)
                else f"{var} = {attrib};\n"
            )

        if isinstance(ins, ir.InstantiateUnion):
            assert isinstance(ins.result.type, ir.UnionType)
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
            membernum = ins.union.type.type_members.index(ins.result.type)
            return f"""
            assert({self.emit_var(ins.union)}.membernum == {membernum});
            {self.emit_var(ins.result)} = {self.emit_var(ins.union)}.val.item{membernum};
            """

        if isinstance(ins, ir.UnSet):
            # TODO: this isn't pretty
            if ins.var.type is STRING:
                return f"{self.emit_var(ins.var)}.buf = NULL;\n"
            if (
                ins.var.type.generic_origin is not None
                and ins.var.type.generic_origin.generic is MAPPING_ITEM
            ):
                return f"{self.emit_var(ins.var)}.hash = 0;\n"
            if isinstance(ins.var.type, UnionType):
                return f"{self.emit_var(ins.var)}.membernum = -1;\n"
            if not ins.var.type.refcounted:
                # Must not run for non-refcounted unions or optionals
                return ""
            return f"{self.emit_var(ins.var)} = NULL;\n"

        if isinstance(ins, ir.Panic):
            return f"""
            panic_printf("%s", string_to_cstr({self.file_pair.emit_string(ins.message)}));
            """

        if isinstance(ins, ir.GotoLabel):
            return _emit_label(self.get_label_name(ins))

        if isinstance(ins, ir.Goto):
            return f"if ({self.emit_var(ins.cond)}) goto {self.get_label_name(ins.label)};\n"

        if isinstance(ins, ir.UnionMemberCheck):
            assert isinstance(ins.union.type, UnionType)
            return f"""
            {self.emit_var(ins.result)} = (
                {self.emit_var(ins.union)}.membernum == {ins.union.type.type_members.index(ins.member_type)}
            );
            """

        raise NotImplementedError(ins)

    def get_label_name(self, label: ir.GotoLabel) -> str:
        if label not in self.label_names:
            self.name_counter += 1
            self.label_names[label] = f"label{self.name_counter}"
        return self.label_names[label]

    def add_local_var(
        self, var: ir.LocalVariable, *, declare: bool = True, need_decref: bool = True
    ) -> None:
        self.name_counter += 1
        name = f"var{self.name_counter}"
        assert var not in self.local_variable_names
        self.local_variable_names[var] = name

        if declare:
            self.before_body += f"{self.file_pair.emit_type(var.type)} {name};\n"
            # TODO: add these in ast2ir?
            self.before_body += self.emit_instruction(ir.UnSet(var))

        if need_decref:
            assert var not in self.need_decref
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


_generic_dir = Path(__file__).absolute().parent.parent / "lib" / "generic"
_generic_paths = {
    LIST: (_generic_dir / "list.c", _generic_dir / "list.h"),
    MAPPING: (_generic_dir / "mapping.c", _generic_dir / "mapping.h"),
    MAPPING_ITEM: (_generic_dir / "mapping_item.c", _generic_dir / "mapping_item.h"),
}


# Represents .c and .h file, and possibly *the* type defined in those.
# That's right, each type goes to separate .c and .h file.
class _FilePair:
    def __init__(self, session: Session, pair_id: str):
        self.id = pair_id  # used in file names and type names
        self.session = session
        self.strings: Dict[str, str] = {}
        self.struct: Optional[str] = None
        self.string_defs = ""
        self.function_decls = ""
        self.function_defs = ""
        self.func_struct_wrapper = _FuncStructWrapper(self)

        # When a _FilePair is in h_includes, the corresponding h_fwd_decls are unnecessary
        self.c_includes: Set[_FilePair] = set()
        self.h_includes: Set[_FilePair] = set()
        self.h_fwd_decls = ""

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.id}>"

    # TODO: can the_type ever be null?
    def emit_type(
        self, the_type: Optional[Type], *, can_fwd_declare_in_header: bool = True
    ) -> str:
        assert not isinstance(the_type, AutoType)
        if the_type is None:
            return "void"
        if the_type is INT:
            return "int64_t"
        if the_type is FLOAT:
            return "double"
        if the_type is BOOL:
            return "bool"
        if the_type is NULL_TYPE:
            return "char"  # always zero
        if the_type is STRING:
            return "struct String"
        assert the_type not in builtin_types.values()

        defining_file_pair = self.session.get_file_pair_for_type(the_type)
        result = f"struct type_{defining_file_pair.id}"

        if _is_pointer(the_type):
            result += "*"
        else:
            can_fwd_declare_in_header = False

        if defining_file_pair is not self:
            self.c_includes.add(defining_file_pair)
            if can_fwd_declare_in_header:
                self.h_fwd_decls += f"struct type_{defining_file_pair.id};\n"
            else:
                self.h_includes.add(defining_file_pair)
        return result

    def emit_var(self, var: ir.Variable) -> str:
        assert not isinstance(var, ir.LocalVariable)

        for symbol in self.session.symbols:
            if symbol.value == var:
                pair = self.session.source_path_to_file_pair[symbol.path]
                if pair is not self:
                    self.c_includes.add(pair)
                    self.h_includes.add(pair)
                    return pair.emit_var(var)

        for name, builtin_var in (
            ir.visible_builtins.items() | ir.hidden_builtins.items()
        ):
            if var == builtin_var:
                return "oomph_" + name.lstrip("_")

        assert isinstance(var.type, FunctionType)
        if isinstance(var, ir.FileVariable) and var.name == "main":
            c_name = "oomph_main"
        elif var.name in {
            "__Bool_to_string",
            "__List_Str_join",
            "__Str___contains",
            "__Str_center_pad",
            "__Str_count",
            "__Str_from_start_to_substring",
            "__Str_get_utf8",
            "__Str_left_pad",
            "__Str_left_trim",
            "__Str_remove_prefix",
            "__Str_remove_suffix",
            "__Str_repeat",
            "__Str_replace",
            "__Str_right_pad",
            "__Str_right_trim",
            "__Str_split",
            "__Str_trim",
        }:
            # Class implemented in C, method implemented in builtins.oomph
            # TODO: check if this file is builtins.oomph
            c_name = "meth_" + var.name.lstrip("_")
        else:
            c_name = self.id + "_" + var.name
        return c_name

    # If body is None, declares but does not actually define
    def define_function(
        self,
        function_name: str,
        the_type: FunctionType,
        argnames: Optional[List[str]] = None,
        body: Optional[str] = None,
    ) -> None:
        if argnames is None:
            arg_decls = list(map(self.emit_type, the_type.argtypes))
        else:
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
        if body is not None:
            self.function_defs += declaration + "{" + body + "}"

    def emit_string(self, value: str) -> str:
        if value not in self.strings:
            # Including the full value in first argument of create_id causes issue #132
            # I like to include some parts of string content for debugging though
            self.strings[value] = _create_id(
                f"string{len(self.strings)}_{value[:20]}", value
            )

            array_content = ", ".join(
                r"'\x%02x'" % byte for byte in value.encode("utf-8")
            )
            self.string_defs += f"""
            static struct StringBuf {self.strings[value]}_buf = {{
                .refcount = -1,
                .data = (char[]){{ {array_content or "0"} }},
                .malloced = false,
                .len = {len(value.encode("utf-8"))},
            }};
            static {self.emit_type(STRING)} {self.strings[value]} = {{
                .buf = &{self.strings[value]}_buf,
                .nbytes = {len(value.encode("utf-8"))},
                .offset = 0,
            }};
            """
        return self.strings[value]

    def _define_union(self, the_type: UnionType) -> None:
        to_string_cases = "".join(
            f"""
            case {num}:
                return meth_{self.session.get_type_c_name(typ)}_to_string(obj.val.item{num});
            """
            for num, typ in enumerate(the_type.type_members)
        )
        equals_cases = "".join(
            f"""
            case {num}:
                return meth_{self.session.get_type_c_name(typ)}_equals(
                    a.val.item{num}, b.val.item{num});
            """
            for num, typ in enumerate(the_type.type_members)
        )
        hash_cases = "".join(
            f"""
            case {num}:
                return meth_{self.session.get_type_c_name(typ)}_hash(obj.val.item{num});
            """
            for num, typ in enumerate(the_type.type_members)
        )

        # TODO: can decls be emitted automatically?
        self.function_decls += f"""
        struct String meth_{self.id}_to_string(struct type_{self.id} obj);
        bool meth_{self.id}_equals(struct type_{self.id} a, struct type_{self.id} b);
        """
        type_name_code = self.emit_string(the_type.name)
        self.function_defs += f"""
        struct String meth_{self.id}_to_string(struct type_{self.id} obj)
        {{
            switch(obj.membernum) {{
                {to_string_cases}
                default:
                    panic_printf(
                        "INTERNAL OOMPH ERROR: invalid %s membernum %d",
                        string_to_cstr({type_name_code}), (int)obj.membernum);
            }}
        }}

        bool meth_{self.id}_equals(struct type_{self.id} a, struct type_{self.id} b)
        {{
            if (a.membernum != b.membernum)
                return false;
            switch(a.membernum) {{
                {equals_cases}
                default:
                    panic_printf(
                        "INTERNAL OOMPH ERROR: invalid %s membernum %d",
                        string_to_cstr({type_name_code}), (int)a.membernum);
            }}
        }}
        """

        # To incref/decref unions, we need to know the value of membernum
        # and incref/decref the correct member of the union. This
        # union-specific function handles that.
        incref_cases = "".join(
            f"""
            case {num}:
                {self.session.emit_incref(f"obj.val.item{num}", typ)};
                break;
            """
            for num, typ in enumerate(the_type.type_members)
        )
        decref_cases = "".join(
            f"""
            case {num}:
                {self.session.emit_decref(f"obj.val.item{num}", typ)};
                break;
            """
            for num, typ in enumerate(the_type.type_members)
        )

        self.function_decls += f"""
        void incref_{self.id}(struct type_{self.id} obj);
        void decref_{self.id}(struct type_{self.id} obj);
        """
        self.function_defs += f"""
        void incref_{self.id}(struct type_{self.id} obj) {{
            switch(obj.membernum) {{
                {incref_cases}
                default:
                    assert(0);
            }}
        }}
        void decref_{self.id}(struct type_{self.id} obj) {{
            switch(obj.membernum) {{
                case -1:   // variable not in use
                    break;
                {decref_cases}
                default:
                    assert(0);
            }}
        }}
        """

        if "hash" in the_type.methods:
            self.function_decls += f"""
            int64_t meth_{self.id}_hash(struct type_{self.id} obj);
            """
            self.function_defs += f"""
            int64_t meth_{self.id}_hash(struct type_{self.id} obj)
            {{
                switch(obj.membernum){{
                    {hash_cases}
                    default:
                        panic_printf("internal error in union hash");
                }}
            }}
            """

        union_members = "".join(
            f"\t{self.emit_type(the_type)} item{index};\n"
            for index, the_type in enumerate(the_type.type_members)
        )

        assert self.struct is None
        self.struct = f"""
        struct type_{self.id} {{
            union {{
                {union_members}
            }} val;
            short membernum;
        }};
        """

    def _define_generic_type(self, the_type: Type) -> None:
        assert the_type.generic_origin is not None
        if the_type.generic_origin.generic == LIST:
            [itemtype] = the_type.generic_origin.args
            macrotypes = [("LIST", the_type), ("ITEM", itemtype)]
        elif the_type.generic_origin.generic == MAPPING:
            keytype, valuetype = the_type.generic_origin.args
            itemtype = MAPPING_ITEM.get_type([keytype, valuetype])
            macrotypes = [
                ("MAPPING", the_type),
                ("KEY", keytype),
                ("VALUE", valuetype),
                ("ITEM", itemtype),
                ("KEY_LIST", LIST.get_type([keytype])),
                ("VALUE_LIST", LIST.get_type([valuetype])),
                ("ITEM_LIST", LIST.get_type([itemtype])),
            ]
        elif the_type.generic_origin.generic == MAPPING_ITEM:
            keytype, valuetype = the_type.generic_origin.args
            macrotypes = [("KEY", keytype), ("VALUE", valuetype), ("ITEM", the_type)]
        else:
            raise RuntimeError(f"unknown generic: {the_type.generic_origin.generic}")

        c_path, h_path = _generic_paths[the_type.generic_origin.generic]
        macro_dict = {}
        for name, macrotype in macrotypes:
            cname = self.session.get_type_c_name(macrotype)
            macro_dict.update(
                {
                    name: self.emit_type(macrotype, can_fwd_declare_in_header=False),
                    f"{name}_STRUCT": f"type_{cname}",
                    f"{name}_CTOR": f"ctor_{cname}",
                    f"{name}_DTOR": f"dtor_{cname}",
                    f"{name}_METHOD(name)": f"meth_{cname}_##name",
                    f"{name}_INCREF(val)": self.session.emit_incref("val", macrotype),
                    f"{name}_DECREF(val)": self.session.emit_decref("val", macrotype),
                    f"{name}_IS_STRING": str(int(macrotype == STRING)),
                }
            )

        defines = "".join(
            f"\n#define {key} {value}\n" for key, value in macro_dict.items()
        )
        undefs = "".join(f"\n#undef {key.split('(')[0]}\n" for key in macro_dict)
        assert self.struct is None
        self.struct = defines + h_path.read_text("utf-8") + undefs
        for name, functype in the_type.methods.items():
            self.define_function(
                f"meth_{self.session.get_type_c_name(the_type)}_{name}", functype
            )
        self.function_defs += defines + c_path.read_text("utf-8") + undefs

    def _define_simple_type(self, the_type: Type) -> None:
        struct_members = "".join(
            f"{self.emit_type(the_type)} memb_{name};\n"
            for name, the_type in the_type.members.items()
        )
        constructor_args = (
            ",".join(
                f"{self.emit_type(the_type)} arg_{name}"
                for name, the_type in the_type.members.items()
            )
            or "void"
        )
        member_assignments = "".join(
            f"obj->memb_{name} = arg_{name};\n" for name in the_type.members
        )
        member_increfs = "".join(
            self.session.emit_incref(f"arg_{name}", the_type) + ";\n"
            for name, the_type in the_type.members.items()
        )
        member_decrefs = "".join(
            self.session.emit_decref(f"obj->memb_{nam}", typ) + ";\n"
            for nam, typ in the_type.members.items()
        )

        assert self.struct is None
        self.struct = f"""
        struct type_{self.id} {{
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
            struct type_{self.id} *obj = ptr;
            {member_decrefs}
            free(obj);
        }}
        """

        for name in the_type.methods_to_create:
            if name == "to_string":
                self.function_decls += f"""
                struct String meth_{self.id}_to_string({self.emit_type(the_type)} obj);
                """
                concats = [
                    f"""
                    tmp = meth_{self.session.get_type_c_name(typ)}_to_string(self->memb_{nam});
                    oomph_string_concat_inplace(&res, tmp);
                    decref_Str(tmp);
                    """
                    for nam, typ in the_type.members.items()
                ]
                concat_comma = 'oomph_string_concat_inplace_cstr(&res, ", ");'
                self.function_defs += f"""
                struct String meth_{self.id}_to_string({self.emit_type(the_type)} self)
                {{
                    struct String res = {self.emit_string(the_type.name)};
                    struct String tmp;
                    oomph_string_concat_inplace_cstr(&res, "(");
                    {concat_comma.join(concats)}
                    oomph_string_concat_inplace_cstr(&res, ")");
                    return res;
                }}
                """
            elif name == "equals":
                self.function_decls += f"""
                // pointer equality
                #define meth_{self.id}_equals(a, b) ((a) == (b))
                """
            elif name == "hash":
                self.function_decls += f"\n#define meth_{self.id}_hash pointer_hash\n"

            else:
                raise NotImplementedError(name)

    def _define_functype(self, functype: FunctionType) -> None:
        assert self.struct is None
        argtypes = ",".join(["void *"] + [self.emit_type(t) for t in functype.argtypes])
        # TODO: make it not named type_Foo, it's not a class
        self.struct = f"""
        struct type_{self.id} {{
            REFCOUNT_HEADER
            {self.emit_type(functype.returntype)} (*func)({argtypes});
            void *data;
            struct DestroyCallback cblist[];  // NULL terminated
        }};
        """

        # TODO: hash method?
        self.function_decls += f"""
        void dtor_{self.id}(void *ptr);
        struct String meth_{self.id}_to_string(const struct type_{self.id} *obj);
        bool meth_{self.id}_equals(const struct type_{self.id} *a, const struct type_{self.id} *b);
        """
        self.function_defs += f"""
        void dtor_{self.id}(void *ptr)
        {{
            struct type_{self.id} *obj = ptr;
            for (const struct DestroyCallback *cb = obj->cblist; cb->func; cb++)
                cb->func(cb->arg);
            free(obj);
        }}

        struct String meth_{self.id}_to_string(const struct type_{self.id} *obj)
        {{
            return cstr_to_string("<function>");  // TODO
        }}

        bool meth_{self.id}_equals(const struct type_{self.id} *a, const struct type_{self.id} *b)
        {{
            return (a == b);   // TODO
        }}
        """

    # Must not be called multiple times for the same _FilePair
    def define_type(self, the_type: Type) -> None:
        if isinstance(the_type, UnionType):
            self._define_union(the_type)
        elif isinstance(the_type, FunctionType):
            self._define_functype(the_type)
        elif the_type.generic_origin is not None:
            self._define_generic_type(the_type)
        else:
            self._define_simple_type(the_type)

    def emit_toplevel_declaration(
        self, top_declaration: ir.ToplevelDeclaration
    ) -> None:
        if isinstance(top_declaration, ir.FuncDef):
            _FunctionEmitter(self).emit_funcdef(
                top_declaration, self.emit_var(top_declaration.var)
            )

        elif isinstance(top_declaration, ir.MethodDef):
            clASS = top_declaration.type.argtypes[0]
            file_pair = self.session.get_file_pair_for_type(clASS)
            _FunctionEmitter(file_pair).emit_funcdef(
                top_declaration,
                f"meth_{self.session.get_type_c_name(clASS)}_{top_declaration.name}",
            )

        else:
            raise NotImplementedError(top_declaration)


# This state is shared between different files
class Session:
    def __init__(self, compilation_dir: Path) -> None:
        self.compilation_dir = compilation_dir
        self.symbols: List[ir.Symbol] = []
        self._type_to_file_pair: Dict[Type, _FilePair] = {}
        self.source_path_to_file_pair: Dict[Path, _FilePair] = {}

    def get_file_pair_for_type(self, the_type: Type) -> _FilePair:
        if the_type not in self._type_to_file_pair:
            pair = _FilePair(self, _create_id(the_type.name, the_type.get_id_string()))
            self._type_to_file_pair[the_type] = pair
            pair.define_type(the_type)
        return self._type_to_file_pair[the_type]

    def get_type_c_name(self, the_type: Type) -> str:
        if the_type is NULL_TYPE:
            return "null"
        if the_type in builtin_types.values():
            return the_type.name
        return self.get_file_pair_for_type(the_type).id

    # May evaluate c_expression several times
    def emit_incref(self, c_expression: str, the_type: Type) -> str:
        if _is_pointer(the_type):
            return f"incref({c_expression})"
        if the_type.refcounted:
            return f"incref_{self.get_type_c_name(the_type)}({c_expression})"
        return "(void)0"

    def emit_decref(self, c_expression: str, the_type: Type) -> str:
        if _is_pointer(the_type):
            return f"decref(({c_expression}), dtor_{self.get_type_c_name(the_type)})"
        if the_type.refcounted:
            return f"decref_{self.get_type_c_name(the_type)}({c_expression})"
        return "(void)0"

    def create_c_code(
        self, top_decls: List[ir.ToplevelDeclaration], source_path: Path
    ) -> None:
        pair = _FilePair(
            self,
            _create_id(
                source_path.stem,
                os.path.relpath(source_path, self.compilation_dir.parent),
            ),
        )
        assert source_path not in self.source_path_to_file_pair
        self.source_path_to_file_pair[source_path] = pair
        for top_declaration in top_decls:
            pair.emit_toplevel_declaration(top_declaration)

    # TODO: don't keep stuff in memory so much
    def write_everything(self, builtins_path: Path) -> List[Path]:
        builtins_pair = self.source_path_to_file_pair[builtins_path]

        c_paths: List[Path] = []
        for file_pair in list(self._type_to_file_pair.values()) + list(
            self.source_path_to_file_pair.values()
        ):
            c_path = self.compilation_dir / (file_pair.id + ".c")
            h_path = self.compilation_dir / (file_pair.id + ".h")
            c_paths.append(c_path)

            c_includes = f'#include <lib/oomph.h>\n#include "{file_pair.id}.h"\n'
            h_includes = "#include <lib/oomph.h>\n"

            if file_pair != builtins_pair:
                c_includes += f'#include "{builtins_pair.id}.h"\n'
                h_includes += f'#include "{builtins_pair.id}.h"\n'

            c_includes += "".join(
                f'#include "{pair.id}.h"\n' for pair in file_pair.c_includes
            )
            h_includes += "".join(
                f'#include "{pair.id}.h"\n' for pair in file_pair.h_includes
            )

            h_code = (
                h_includes
                + file_pair.h_fwd_decls
                + (file_pair.struct or "")
                + file_pair.function_decls
            )
            c_code = c_includes + file_pair.string_defs + file_pair.function_defs

            header_guard = "HEADER_GUARD_" + file_pair.id
            c_path.write_text(c_code + "\n", encoding="utf-8")
            h_path.write_text(
                f"""
                #ifndef {header_guard}
                #define {header_guard}
                {h_code}
                #endif
                \n""",
                encoding="utf-8",
            )

        return c_paths
