import pathlib
import re
from typing import Callable, Iterator, List, Optional, Tuple, TypeVar, Union

import more_itertools

from pyoomph import tokenizer
from pyoomph import untyped_ast as uast

_T = TypeVar("_T")


class _Parser:
    def __init__(self, token_iter: Iterator[Tuple[str, str]]):
        self.token_iter = more_itertools.peekable(token_iter)
        self.foreach_counter = 0

    def get_token(
        self,
        required_type: Optional[str] = None,
        required_value: Optional[str] = None,
    ) -> Tuple[str, str]:
        tokentype, value = next(self.token_iter)
        if required_type is not None:
            assert tokentype == required_type, (
                required_type,
                required_value,
                tokentype,
                value,
            )
        if required_value is not None:
            assert value == required_value, (
                required_type,
                required_value,
                tokentype,
                value,
            )
        return (tokentype, value)

    def parse_import(
        self, path_of_this_file: pathlib.Path, stdlib: pathlib.Path
    ) -> uast.Import:
        self.get_token("keyword", "import")
        string = self.get_token("oneline_string")[1]
        self.get_token("keyword", "as")
        name = self.get_token("identifier")[1]
        self.get_token("op", "\n")

        assert "\\" not in string and "{" not in string and "}" not in string
        if string.startswith('"<stdlib>/'):
            path = stdlib / string.strip('"').split("/", 1)[1]
        else:
            path = path_of_this_file.parent / string.strip('"')
        return uast.Import(path, name)

    def parse_commasep_in_parens(self, content_callback: Callable[[], _T]) -> List[_T]:
        self.get_token("op", "(")
        result = []
        if self.token_iter.peek() != ("op", ")"):
            result.append(content_callback())
            while self.token_iter.peek() == ("op", ","):
                self.get_token("op", ",")
                result.append(content_callback())
        self.get_token("op", ")")
        return result

    def tokenize_and_parse_expression(self, code: str) -> uast.Expression:
        parser = _Parser(tokenizer.tokenize(code))
        result = parser.parse_expression()
        parser.get_token("op", "\n")
        assert not parser.token_iter, parser.token_iter.peek()
        return result

    def do_string_formatting(self, string: str) -> uast.Expression:
        parts = []
        while string:
            if string[0] == "{":
                end = string.index("}")
                parts.append(self.tokenize_and_parse_expression(string[1:end]))
                string = string[end + 1 :]
            else:
                match = re.search(r"(?<!\\)\{", string)
                text_end = len(string) if match is None else match.start()
                parts.append(
                    uast.StringConstant(
                        string[:text_end]
                        .replace("\\n", "\n")
                        .replace("\\t", "\t")
                        .replace("\\{", "{")
                        .replace("\\}", "}")
                        .replace("\\\\", "\\")
                    )
                )
                string = string[text_end:]

        if len(parts) == 0:
            return uast.StringConstant("")
        if len(parts) == 1:
            return parts[0]
        return uast.StringFormatJoin(parts)

    def parse_simple_expression(self) -> uast.Expression:
        result: uast.Expression
        if self.token_iter.peek()[0] == "oneline_string":
            result = self.do_string_formatting(
                self.get_token("oneline_string")[1][1:-1]
            )
        elif self.token_iter.peek()[0] == "multiline_string":
            result = self.do_string_formatting(
                self.get_token("multiline_string")[1][3:-3]
            )
        elif self.token_iter.peek()[0] == "identifier":
            result = uast.GetVar(self.get_token("identifier")[1])
        elif self.token_iter.peek()[0] == "int":
            result = uast.IntConstant(int(self.get_token("int")[1]))
        elif self.token_iter.peek()[0] == "float":
            result = uast.FloatConstant(self.get_token("float")[1])
        elif self.token_iter.peek()[0].startswith("assert_"):  # TODO: is haxor
            lineno = int(self.token_iter.peek()[0].split("_")[1])
            result = uast.GetVar(self.get_token()[1], lineno)
        elif self.token_iter.peek() == ("keyword", "new"):
            self.get_token("keyword", "new")
            result = uast.Constructor(self.parse_type())
        elif self.token_iter.peek() == ("keyword", "null"):
            self.get_token("keyword", "null")
            self.get_token("op", "[")
            result = uast.Null(self.parse_type())
            self.get_token("op", "]")
        elif self.token_iter.peek() == ("op", "("):
            self.get_token("op", "(")
            result = self.parse_expression()
            self.get_token("op", ")")
        else:
            raise NotImplementedError(self.token_iter.peek())

        while True:
            if self.token_iter.peek() == ("op", "("):
                result = uast.Call(
                    result, self.parse_commasep_in_parens(self.parse_expression)
                )
            elif self.token_iter.peek() == ("op", "."):
                self.get_token("op", ".")
                result = uast.GetAttribute(result, self.get_token("identifier")[1])
            else:
                return result

    def get_unary_operators(self) -> Iterator[Tuple[int, str]]:
        while self.token_iter.peek() in {("keyword", "not"), ("op", "-")}:
            yield (1, self.get_token()[1])

    def parse_expression(self) -> uast.Expression:
        magic_list: List[Union[Tuple[int, str], uast.Expression]] = []
        magic_list.extend(self.get_unary_operators())
        magic_list.append(self.parse_simple_expression())

        while self.token_iter.peek() in {
            ("op", "+"),
            ("op", "-"),
            ("op", "*"),
            ("op", "/"),
            ("op", "=="),
            ("op", "!="),
            ("op", "<"),
            ("op", ">"),
            ("op", "<="),
            ("op", ">="),
            ("keyword", "and"),
            ("keyword", "or"),
            ("keyword", "mod"),
        }:
            magic_list.append((2, self.get_token()[1]))
            magic_list.extend(self.get_unary_operators())
            magic_list.append(self.parse_simple_expression())

        # A common python beginner mistake is writing "a and b or c", thinking it
        # means "a and (b or c)"
        assert not ((2, "and") in magic_list and (2, "or") in magic_list), (
            "instead of 'a and b or c', write '(a and b) or c', "
            "or write 'a and (b or c)'"
        )

        # a==b==c is not supported yet
        # FIXME: this test is broken for a == -b == c
        assert not any(
            first in [(2, "=="), (2, "!=")] and second in [(2, "=="), (2, "!=")]
            for first, second in zip(magic_list, magic_list[2:])
        )

        # Disallow a--b and --a, require a-(-b) or -(-a)
        assert not any(
            first in [(1, "-"), (2, "-")] and second == (1, "-")
            for first, second in zip(magic_list, magic_list[1:])
        )

        # TODO: warning about 'x == y mod 3' which is likely intended to be 'x mod 3 == y mod 3'

        # each operator of a group is considered to have same precedence
        for op_group in [
            [(2, "*"), (2, "/")],
            [(2, "+"), (2, "-"), (1, "-")],
            [(2, "mod")],
            [(2, "=="), (2, "!=")],
            [(2, "<"), (2, ">"), (2, "<="), (2, ">=")],
            [(1, "not")],
            [(2, "and"), (2, "or")],
        ]:
            while any(op in magic_list for op in op_group):
                where = min(magic_list.index(op) for op in op_group if op in magic_list)
                op = magic_list[where]
                assert isinstance(op, tuple)
                op_kind, op_string = op

                if op_kind == 1:  # Unary operator
                    operand = magic_list[where + 1]
                    assert isinstance(operand, uast.Expression)
                    magic_list[where : where + 2] = [
                        uast.UnaryOperator(op_string, operand)
                    ]
                elif op_kind == 2:  # Binary operator
                    lhs = magic_list[where - 1]
                    rhs = magic_list[where + 1]
                    assert isinstance(lhs, uast.Expression)
                    assert isinstance(rhs, uast.Expression)
                    magic_list[where - 1 : where + 2] = [
                        uast.BinaryOperator(lhs, op_string, rhs)
                    ]
                else:
                    raise NotImplementedError(op_kind)

        [expr] = magic_list
        assert isinstance(expr, uast.Expression)
        return expr

    def parse_block(self, callback: Callable[[], _T]) -> List[_T]:
        self.get_token("begin_block", ":")
        result = []
        while self.token_iter and self.token_iter.peek(None) != ("end_block", ""):
            result.append(callback())
        self.get_token("end_block", "")
        return result

    def parse_block_of_statements(self) -> List[uast.Statement]:
        result = []
        for statement_list in self.parse_block(self.parse_statement):
            result.extend(statement_list)
        return result

    def parse_oneline_ish_statement(self) -> uast.Statement:
        if self.token_iter.peek() == ("keyword", "let"):
            self.get_token("keyword", "let")
            varname = self.get_token("identifier")[1]
            self.get_token("op", "=")
            value = self.parse_expression()
            return uast.Let(varname, value)

        if self.token_iter.peek() == ("keyword", "return"):
            self.get_token("keyword", "return")
            # This is a weird way to check whether an expression is coming up.
            # It doesn't work in e.g. first line of for loop, but if you think
            # that returning there is a good idea, then wtf lol.
            if self.token_iter.peek() == ("op", "\n"):
                return uast.Return(None)
            return uast.Return(self.parse_expression())

        if self.token_iter.peek() == ("keyword", "pass"):
            self.get_token("keyword", "pass")
            return uast.Pass()

        if self.token_iter.peek() == ("keyword", "continue"):
            self.get_token("keyword", "continue")
            return uast.Continue()

        if self.token_iter.peek() == ("keyword", "break"):
            self.get_token("keyword", "break")
            return uast.Break()

        expr = self.parse_expression()
        if isinstance(expr, uast.GetVar) and self.token_iter.peek(None) == ("op", "="):
            self.get_token("op", "=")
            value = self.parse_expression()
            return uast.Assign(expr.varname, value)

        assert isinstance(expr, uast.Call), expr
        return expr

    def parse_case(self) -> Tuple[uast.Type, List[uast.Statement]]:
        self.get_token("keyword", "case")
        the_type = self.parse_type()
        body = self.parse_block_of_statements()
        return (the_type, body)

    def foreach_loop_to_for_loop(
        self, varname: str, the_list: uast.Expression, body: List[uast.Statement]
    ) -> List[uast.Statement]:
        list_var = f"__foreach_list_{self.foreach_counter}"
        index_var = f"__foreach_index_{self.foreach_counter}"
        self.foreach_counter += 1

        let: uast.Statement = uast.Let(
            varname,
            uast.Call(
                uast.GetAttribute(uast.GetVar(list_var), "get"),
                [uast.GetVar(index_var)],
            ),
        )
        return [
            uast.Let(index_var, uast.IntConstant(0)),
            uast.Let(list_var, the_list),
            uast.Loop(
                None,
                uast.BinaryOperator(
                    uast.GetVar(index_var),
                    "<",
                    uast.Call(uast.GetAttribute(uast.GetVar(list_var), "length"), []),
                ),
                uast.Assign(
                    index_var,
                    uast.BinaryOperator(
                        uast.GetVar(index_var), "+", uast.IntConstant(1)
                    ),
                ),
                [let] + body,
            ),
        ]

    def parse_statement(self) -> List[uast.Statement]:
        if self.token_iter.peek() == ("keyword", "if"):
            self.get_token("keyword", "if")
            condition = self.parse_expression()
            body = self.parse_block_of_statements()
            ifs = [(condition, body)]

            while self.token_iter.peek() == ("keyword", "elif"):
                self.get_token("keyword", "elif")
                condition = self.parse_expression()
                body = self.parse_block_of_statements()
                ifs.append((condition, body))

            if self.token_iter.peek() == ("keyword", "else"):
                self.get_token("keyword", "else")
                else_body = self.parse_block_of_statements()
            else:
                else_body = []

            return [uast.If(ifs, else_body)]

        if self.token_iter.peek() == ("keyword", "while"):
            self.get_token("keyword", "while")
            cond: Optional[uast.Expression] = self.parse_expression()
            body = self.parse_block_of_statements()
            return [uast.Loop(None, cond, None, body)]

        if self.token_iter.peek() == ("keyword", "for"):
            self.get_token("keyword", "for")
            init = (
                None
                if self.token_iter.peek() == ("op", ";")
                else self.parse_oneline_ish_statement()
            )
            self.get_token("op", ";")
            cond = (
                None
                if self.token_iter.peek() == ("op", ";")
                else self.parse_expression()
            )
            self.get_token("op", ";")
            incr = (
                None
                if self.token_iter.peek() == ("op", ";")
                else self.parse_oneline_ish_statement()
            )
            body = self.parse_block_of_statements()
            return [uast.Loop(init, cond, incr, body)]

        if self.token_iter.peek() == ("keyword", "foreach"):
            self.get_token("keyword", "foreach")
            varname = self.get_token("identifier")[1]
            self.get_token("keyword", "of")
            the_list = self.parse_expression()
            body = self.parse_block_of_statements()
            return self.foreach_loop_to_for_loop(varname, the_list, body)

        if self.token_iter.peek() == ("keyword", "switch"):
            self.get_token("keyword", "switch")
            varname = self.get_token("identifier")[1]
            cases = self.parse_block(self.parse_case)
            return [uast.Switch(varname, dict(cases))]

        result = self.parse_oneline_ish_statement()
        self.get_token("op", "\n")
        return [result]

    def parse_type(self) -> uast.Type:
        name = self.get_token("identifier")[1]
        generic = None
        if self.token_iter.peek() == ("op", "["):
            self.get_token("op", "[")
            generic = self.parse_type()
            self.get_token("op", "]")
        return uast.Type(name, generic)

    def parse_funcdef_arg(self) -> Tuple[uast.Type, str]:
        type_name = self.parse_type()
        arg_name = self.get_token("identifier")[1]
        return (type_name, arg_name)

    def parse_function_or_method(self) -> uast.FuncOrMethodDef:
        name = self.get_token("identifier")[1]
        args = self.parse_commasep_in_parens(self.parse_funcdef_arg)

        if self.token_iter.peek() == ("op", "->"):
            self.get_token("op", "->")
            returntype: Optional[uast.Type] = self.parse_type()
        else:
            returntype = None

        return uast.FuncOrMethodDef(
            name, args, returntype, self.parse_block_of_statements()
        )

    def parse_method(self) -> uast.FuncOrMethodDef:
        self.get_token("keyword", "meth")
        return self.parse_function_or_method()

    def parse_union_member(self) -> uast.Type:
        result = self.parse_type()
        self.get_token("op", "\n")
        return result

    def parse_toplevel(self) -> uast.ToplevelDeclaration:
        if self.token_iter.peek() == ("keyword", "export"):
            self.get_token("keyword", "export")
            export = True
        else:
            export = False

        if self.token_iter.peek() == ("keyword", "func"):
            self.get_token("keyword", "func")
            result = self.parse_function_or_method()
            result.export = export
            return result

        if self.token_iter.peek() == ("keyword", "class"):
            self.get_token("keyword", "class")
            name = self.get_token("identifier")[1]
            args = self.parse_commasep_in_parens(self.parse_funcdef_arg)
            if self.token_iter.peek(None) == ("begin_block", ":"):
                body = self.parse_block(self.parse_method)
            else:
                body = []
                self.get_token("op", "\n")
            return uast.ClassDef(name, args, body, export)

        if self.token_iter.peek() == ("keyword", "union"):
            self.get_token("keyword", "union")
            name = self.get_token("identifier")[1]
            types = self.parse_block(self.parse_union_member)
            return uast.UnionDef(name, types, export)

        raise NotImplementedError(self.token_iter.peek())


def parse_file(
    code: str, path: Optional[pathlib.Path], stdlib: Optional[pathlib.Path]
) -> List[uast.ToplevelDeclaration]:
    parser = _Parser(tokenizer.tokenize(code))

    result: List[uast.ToplevelDeclaration] = []
    while parser.token_iter.peek(None) == ("keyword", "import"):
        assert path is not None
        assert stdlib is not None
        result.append(parser.parse_import(path, stdlib))
    while parser.token_iter:
        result.append(parser.parse_toplevel())

    return result
