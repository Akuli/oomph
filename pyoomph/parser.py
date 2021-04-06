import pathlib
import re
from typing import Callable, Iterator, List, Optional, Tuple, TypeVar, Union

import more_itertools

from pyoomph import ast, tokenizer

_T = TypeVar("_T")


class _Parser:
    def __init__(self, token_iter: Iterator[Tuple[str, str]]):
        self.token_iter = more_itertools.peekable(token_iter)

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
    ) -> ast.Import:
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
        return ast.Import(path, name)

    def parse_commasep_in_parens(
        self, content_callback: Callable[[], _T], *, parens: str = "()"
    ) -> List[_T]:
        left, right = list(parens)
        self.get_token("op", left)
        result = []
        if self.token_iter.peek() != ("op", right):
            result.append(content_callback())
            while self.token_iter.peek() == ("op", ","):
                self.get_token("op", ",")
                if self.token_iter.peek() == ("op", right):
                    break
                result.append(content_callback())
        self.get_token("op", right)
        return result

    def tokenize_and_parse_expression(self, code: str) -> ast.Expression:
        parser = _Parser(tokenizer.tokenize(code))
        result = parser.parse_expression()
        parser.get_token("op", "\n")
        assert not parser.token_iter, parser.token_iter.peek()
        return result

    def do_string_formatting(self, string: str) -> ast.Expression:
        parts = []
        while string:
            if string[0] == "{":
                end = string.index("}")
                parts.append(self.tokenize_and_parse_expression(string[1:end]))
                string = string[end + 1 :]
            elif string.startswith("\\"):
                parts.append(
                    ast.StringConstant(
                        {
                            r"\n": "\n",
                            r"\t": "\t",
                            r"\{": "{",
                            r"\}": "}",
                            r"\"": '"',
                            r"\\": "\\",
                        }[string[:2]]
                    )
                )
                string = string[2:]
            else:
                match = re.match(r"[^{}\\]+", string)
                assert match is not None
                parts.append(ast.StringConstant(match.group(0)))
                string = string[len(match.group(0)) :]

        if len(parts) == 0:
            return ast.StringConstant("")
        if len(parts) == 1:
            return parts[0]
        return ast.StringFormatJoin(parts)

    def parse_loop_header(self) -> Union[ast.ForLoopHeader, ast.ForeachLoopHeader]:
        if self.token_iter.peek() == ("keyword", "while"):
            self.get_token("keyword", "while")
            return ast.ForLoopHeader([], self.parse_expression(), [])

        if self.token_iter.peek() == ("keyword", "for"):
            self.get_token("keyword", "for")
            init = (
                []
                if self.token_iter.peek() == ("op", ";")
                else [self.parse_oneline_ish_statement()]
            )
            self.get_token("op", ";")
            cond = (
                None
                if self.token_iter.peek() == ("op", ";")
                else self.parse_expression()
            )
            self.get_token("op", ";")
            incr = (
                []
                if self.token_iter.peek() == ("begin_block", ":")
                else [self.parse_oneline_ish_statement()]
            )
            return ast.ForLoopHeader(init, cond, incr)

        if self.token_iter.peek() == ("keyword", "foreach"):
            self.get_token("keyword", "foreach")
            varname = self.get_token("identifier")[1]
            self.get_token("keyword", "of")
            return ast.ForeachLoopHeader(varname, self.parse_expression())

        raise NotImplementedError(self.token_iter.peek())

    def parse_simple_expression(self) -> ast.Expression:
        result: ast.Expression
        if self.token_iter.peek()[0] == "oneline_string":
            result = self.do_string_formatting(
                self.get_token("oneline_string")[1][1:-1]
            )
        elif self.token_iter.peek()[0] == "multiline_string":
            result = self.do_string_formatting(
                self.get_token("multiline_string")[1][3:-3]
            )
        elif self.token_iter.peek()[0] == "identifier":
            result = ast.GetVar(self.get_token("identifier")[1])
        elif self.token_iter.peek()[0] == "int":
            result = ast.IntConstant(int(self.get_token("int")[1]))
        elif self.token_iter.peek()[0] == "float":
            result = ast.FloatConstant(self.get_token("float")[1])
        elif self.token_iter.peek()[0].startswith("assert_"):  # TODO: is haxor
            lineno = int(self.token_iter.peek()[0].split("_")[1])
            result = ast.GetVar(self.get_token()[1], lineno)
        elif self.token_iter.peek() == ("keyword", "new"):
            self.get_token("keyword", "new")
            result = ast.Constructor(self.parse_type())
        elif self.token_iter.peek() == ("op", "("):
            self.get_token("op", "(")
            result = self.parse_expression()
            self.get_token("op", ")")
        elif self.token_iter.peek() == ("op", "["):
            if self.token_iter[1] in {
                ("keyword", "while"),
                ("keyword", "for"),
                ("keyword", "foreach"),
            }:
                # list comprehension
                self.get_token("op", "[")
                loop_header = self.parse_loop_header()
                self.get_token("op", ":")
                value = self.parse_expression()
                self.get_token("op", "]")
                result = ast.ListComprehension(loop_header, value)
            else:
                result = ast.ListLiteral(
                    self.parse_commasep_in_parens(self.parse_expression, parens="[]")
                )
        else:
            raise NotImplementedError(self.token_iter.peek())

        while True:
            if self.token_iter.peek() == ("op", "("):
                result = ast.Call(
                    result, self.parse_commasep_in_parens(self.parse_expression)
                )
            elif self.token_iter.peek() == ("op", "."):
                self.get_token("op", ".")
                result = ast.GetAttribute(result, self.get_token("identifier")[1])
            else:
                return result

    def get_unary_operators(self) -> Iterator[Tuple[int, str]]:
        while self.token_iter.peek() in {("keyword", "not"), ("op", "-")}:
            yield (1, self.get_token()[1])

    def parse_expression(self) -> ast.Expression:
        magic_list: List[Union[Tuple[int, str], ast.Expression, ast.Type]] = []
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
            ("keyword", "in"),
            ("keyword", "not in"),
            ("keyword", "and"),
            ("keyword", "or"),
            ("keyword", "as"),
            ("keyword", "mod"),
        }:
            keyword = self.get_token()[1]
            magic_list.append((2, keyword))
            if keyword == "as":
                magic_list.append(self.parse_type())
            else:
                magic_list.extend(self.get_unary_operators())
                magic_list.append(self.parse_simple_expression())

        # each operator of a group is considered to have same precedence
        for op_group in [
            [(2, "*"), (2, "/")],
            [(2, "+"), (2, "-"), (1, "-")],
            [(2, "mod")],
            [(2, "=="), (2, "!=")],
            [(2, "<"), (2, ">"), (2, "<="), (2, ">=")],
            [(2, "as")],
            [(2, "in"), (2, "not in")],
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
                    assert isinstance(operand, ast.Expression)
                    magic_list[where : where + 2] = [
                        ast.UnaryOperator(op_string, operand)
                    ]
                elif op_kind == 2:  # Binary operator
                    lhs = magic_list[where - 1]
                    rhs = magic_list[where + 1]
                    if op_string == "as":
                        assert isinstance(lhs, ast.Expression)
                        assert isinstance(rhs, ast.Type)
                        result: ast.Expression = ast.As(lhs, rhs)
                    else:
                        assert isinstance(lhs, ast.Expression)
                        assert isinstance(rhs, ast.Expression)
                        result = ast.BinaryOperator(lhs, op_string, rhs)
                    magic_list[where - 1 : where + 2] = [result]
                else:
                    raise NotImplementedError(op_kind)

        [expr] = magic_list
        assert isinstance(expr, ast.Expression)
        return expr

    def parse_block(self, callback: Callable[[], _T]) -> List[_T]:
        self.get_token("begin_block", ":")
        result = []
        while self.token_iter and self.token_iter.peek(None) != ("end_block", ""):
            result.append(callback())
        self.get_token("end_block", "")
        return result

    def parse_block_of_statements(self) -> List[ast.Statement]:
        result = []
        for statement_list in self.parse_block(self.parse_statement):
            result.extend(statement_list)
        return result

    def parse_oneline_ish_statement(self) -> ast.Statement:
        if self.token_iter.peek() == ("keyword", "let"):
            self.get_token("keyword", "let")
            varname = self.get_token("identifier")[1]
            self.get_token("op", "=")
            value = self.parse_expression()
            return ast.Let(varname, value)

        if self.token_iter.peek() == ("keyword", "return"):
            self.get_token("keyword", "return")
            # This is a weird way to check whether an expression is coming up.
            # It doesn't work in e.g. first line of for loop, but if you think
            # that returning there is a good idea, then wtf lol.
            if self.token_iter.peek() == ("op", "\n"):
                return ast.Return(None)
            return ast.Return(self.parse_expression())

        if self.token_iter.peek() == ("keyword", "pass"):
            self.get_token("keyword", "pass")
            return ast.Pass()

        if self.token_iter.peek() == ("keyword", "continue"):
            self.get_token("keyword", "continue")
            return ast.Continue()

        if self.token_iter.peek() == ("keyword", "break"):
            self.get_token("keyword", "break")
            return ast.Break()

        expr = self.parse_expression()
        if self.token_iter.peek(None) == (
            "op",
            "=",
        ):
            self.get_token("op", "=")
            value = self.parse_expression()
            if isinstance(expr, ast.GetVar):
                return ast.SetVar(expr.varname, value)
            if isinstance(expr, ast.GetAttribute):
                return ast.SetAttribute(expr.obj, expr.attribute, value)
            raise RuntimeError(f"can't assign to {expr}")

        assert isinstance(expr, ast.Call), expr
        return expr

    def parse_case(self) -> ast.Case:
        self.get_token("keyword", "case")
        if self.token_iter.peek() == ("op", "*"):
            self.get_token("op", "*")
            type_and_varname = None
        else:
            type_and_varname = self.parse_funcdef_arg()
        body = self.parse_block_of_statements()
        return ast.Case(type_and_varname, body)

    def parse_statement(self) -> List[ast.Statement]:
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

            return [ast.If(ifs, else_body)]

        if self.token_iter.peek() in {
            ("keyword", "while"),
            ("keyword", "for"),
            ("keyword", "foreach"),
        }:
            header = self.parse_loop_header()
            body = self.parse_block_of_statements()
            return [ast.Loop(header, body)]

        if self.token_iter.peek() == ("keyword", "switch"):
            self.get_token("keyword", "switch")
            union_obj = self.parse_expression()
            cases = self.parse_block(self.parse_case)
            return [ast.Switch(union_obj, cases)]

        result = self.parse_oneline_ish_statement()
        self.get_token("op", "\n")
        return [result]

    def parse_type_without_unions(self) -> ast.Type:
        if self.token_iter.peek() == ("op", "("):
            self.get_token("op", "(")
            result = self.parse_type()
            self.get_token("op", ")")
            return result

        if self.token_iter.peek() == ("keyword", "auto"):
            self.get_token("keyword", "auto")
            return ast.AutoType()

        name = self.get_token("identifier")[1]
        if self.token_iter.peek() == ("op", "["):
            self.get_token("op", "[")
            arg = self.parse_type()
            self.get_token("op", "]")
            return ast.GenericType(name, arg)

        return ast.NamedType(name)

    def parse_type(self) -> ast.Type:
        first_member = self.parse_type_without_unions()
        if self.token_iter.peek() != ("op", "|"):
            return first_member

        result = ast.UnionType([first_member])
        while self.token_iter.peek() == ("op", "|"):
            self.get_token("op", "|")
            result.unioned.append(self.parse_type_without_unions())
        return result

    def parse_funcdef_arg(self) -> Tuple[ast.Type, str]:
        type_name = self.parse_type()
        arg_name = self.get_token("identifier")[1]
        return (type_name, arg_name)

    def parse_function_or_method(self) -> ast.FuncOrMethodDef:
        name = self.get_token("identifier")[1]
        args = self.parse_commasep_in_parens(self.parse_funcdef_arg)

        if self.token_iter.peek() == ("op", "->"):
            self.get_token("op", "->")
            # Don't really support 'noreturn', but make sure that programs compile
            if self.token_iter.peek() == ("keyword", "noreturn"):
                self.get_token("keyword", "noreturn")
                returntype: Optional[ast.Type] = None
            else:
                returntype = self.parse_type()
        else:
            returntype = None

        return ast.FuncOrMethodDef(
            name, args, returntype, self.parse_block_of_statements()
        )

    def parse_method(self) -> ast.FuncOrMethodDef:
        self.get_token("keyword", "meth")
        return self.parse_function_or_method()

    def parse_toplevel(self) -> ast.ToplevelDeclaration:
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
            return ast.ClassDef(name, args, body, export)

        if self.token_iter.peek() == ("keyword", "typedef"):
            self.get_token("keyword", "typedef")
            name = self.get_token("identifier")[1]
            assert "::" not in name
            self.get_token("op", "=")
            the_type = self.parse_type()
            self.get_token("op", "\n")
            return ast.TypeDef(name, the_type)

        raise NotImplementedError(self.token_iter.peek())


def parse_file(
    code: str, path: pathlib.Path, stdlib: Optional[pathlib.Path]
) -> List[ast.ToplevelDeclaration]:
    parser = _Parser(tokenizer.tokenize(code))

    result: List[ast.ToplevelDeclaration] = []
    while parser.token_iter.peek(None) == ("keyword", "import"):
        assert stdlib is not None
        result.append(parser.parse_import(path, stdlib))
    while parser.token_iter:
        result.append(parser.parse_toplevel())

    return result
