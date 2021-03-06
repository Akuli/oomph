from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple, Union

import oomphmini.typed_ast as tast
from oomphmini.types import STRING, FunctionType, Type


class _FunctionEmitter:
    def __init__(self, file_emitter: _FileEmitter) -> None:
        self.file_emitter = file_emitter
        self.variable_names = self.file_emitter.variable_names.copy()
        self.before_body = ""
        self.after_body = ""

    def add_local_var(self, var: tast.LocalVariable) -> None:
        # Ensure different functions don't share variable names.
        # This makes grepping the C code easier.
        name = self.file_emitter.get_var_name()
        assert var not in self.variable_names
        self.variable_names[var] = name
        self.before_body += f"{self.file_emitter.emit_type(var.type)} {name};\n\t"

    def create_local_var(self, the_type: Type) -> tast.LocalVariable:
        var = tast.LocalVariable("c_output_var", the_type)
        self.add_local_var(var)
        return var

    def emit_call(self, ast: Union[tast.ReturningCall, tast.VoidCall]) -> str:
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
        if isinstance(ast, tast.GetVar):
            return self.variable_names[ast.var]
        raise NotImplementedError(ast)

    def emit_label(self, name: str) -> str:
        # It's invalid c syntax to end a block with a label, (void)0 fixes
        return f"{name}: (void)0;\n\t"

    def emit_statement(self, ast: tast.Statement) -> str:
        if isinstance(ast, (tast.ReturningCall, tast.VoidCall)):
            return self.emit_call(ast) + ";\n\t"
        raise NotImplementedError(ast)

    def emit_funcdef(
        self,
        funcdef: tast.FuncDef,
        c_name: str,
    ) -> None:
        assert not funcdef.argvars
        assert not funcdef.refs

        body_statements = "".join(self.emit_statement(s) for s in funcdef.body)
        assert isinstance(funcdef.var.type, FunctionType)
        functype = funcdef.var.type

        assert functype.returntype is None
        assert not self.after_body
        self.file_emitter.define_function(
            c_name,
            functype,
            [],
            self.before_body + body_statements + self.emit_label("out"),
        )


class _FileEmitter:
    def __init__(
        self,
        session: Session,
    ):
        self.session = session
        self.varname_counter = 0
        self.variable_names: Dict[tast.Variable, str] = {
            tast.builtin_variables["print"]: "io_print",
        }
        self.strings: Dict[str, str] = {}

        self.function_decls = ""
        self.function_defs = ""
        self.string_defs = ""

    def define_function(
        self, function_name: str, the_type: FunctionType, argnames: List[str], body: str
    ) -> None:
        assert not argnames
        assert not the_type.argtypes
        declaration = "%s %s(void)" % (
            self.emit_type(the_type.returntype),
            function_name,
        )
        self.function_decls += declaration + ";"
        self.function_defs += declaration + "{" + body + "}"

    def get_var_name(self) -> str:
        self.varname_counter += 1
        return f"var{self.varname_counter}"

    def get_type_c_name(self, the_type: Type) -> str:
        return the_type.name

    def emit_type(self, the_type: Optional[Type]) -> str:
        if the_type is None:
            return "void"
        assert the_type.refcounted
        return f"struct class_{self.get_type_c_name(the_type)} *"

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
        self, top_declaration: tast.ToplevelDeclaration
    ) -> None:
        if isinstance(top_declaration, tast.FuncDef):
            assert (
                isinstance(top_declaration.var, tast.ExportVariable)
                and top_declaration.var.name == "main"
            )
            c_name = "oomph_main"

            self.variable_names[top_declaration.var] = c_name

            _FunctionEmitter(self).emit_funcdef(
                top_declaration,
                self.variable_names[top_declaration.var],
            )

        else:
            raise NotImplementedError(top_declaration)


class Session:
    def __init__(self) -> None:
        self.exports: List[tast.Export] = []
        self.export_c_names: Dict[tast.Export, str] = {}

    def create_c_code(
        self,
        ast: List[tast.ToplevelDeclaration],
    ) -> Tuple[str, str]:
        includes = "#include <lib/oomph.h>\n"

        emitter = _FileEmitter(self)
        for top_declaration in ast:
            emitter.emit_toplevel_declaration(top_declaration)

        c_code = includes + emitter.string_defs + emitter.function_defs
        return (
            c_code,
            f"""
            #ifndef HEADER
            #define HEADER
            {includes}
            #endif""",
        )
