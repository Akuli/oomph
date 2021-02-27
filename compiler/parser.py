from typing import Callable, Iterable, Iterator, List, Optional, Tuple, TypeVar, Union

import more_itertools

from compiler import untyped_ast as uast

_T = TypeVar("_T")


class _Parser:
    def __init__(self, token_iter: 'more_itertools.peekable[Tuple[str, str]]'):
        self.token_iter = token_iter

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

    def parse_expression_without_operators(self) -> uast.Expression:
        result: uast.Expression
        if self.token_iter.peek()[0] == "identifier":
            result = uast.GetVar(self.get_token("identifier")[1])
        elif self.token_iter.peek()[0] == "int":
            result = uast.IntConstant(int(self.get_token("int")[1]))
        elif self.token_iter.peek()[0] == "float":
            result = uast.FloatConstant(self.get_token("float")[1])
        elif self.token_iter.peek() == ("keyword", "new"):
            self.get_token("keyword", "new")
            result = uast.Constructor(self.parse_type())
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
        magic_list.append(self.parse_expression_without_operators())

        while self.token_iter.peek() in {
            ("op", "+"),
            ("op", "-"),
            ("op", "*"),
            ("op", "/"),
            ("op", "=="),
            ("op", "!="),
            ("keyword", "and"),
            ("keyword", "or"),
        }:
            magic_list.append((2, self.get_token()[1]))
            magic_list.extend(self.get_unary_operators())
            magic_list.append(self.parse_expression_without_operators())

        # A common python beginner mistake is writing "a and b or c", thinking it
        # means "a and (b or c)"
        assert not ("and" in magic_list and "or" in magic_list)

        # a==b==c is not supported yet
        assert not any(
            first in [(2, "=="), (2, "!=")] and second in [(2, "=="), (2, "!=")]
            for first, second in zip(magic_list, magic_list[2:])
        )

        # Disallow a--b and --a, require a-(-b) or -(-a)
        assert not any(
            first in [(1, "-"), (2, "-")] and second == (1, "-")
            for first, second in zip(magic_list, magic_list[1:])
        )

        # each operator of a group is considered to have same precedence
        for op_group in [
            [(2, "*"), (2, "/")],
            [(2, "+"), (2, "-"), (1, "-")],
            [(2, "=="), (2, "!=")],
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

    def parse_oneline_ish_statement(self) -> uast.Statement:
        if self.token_iter.peek() == ("keyword", "let"):
            self.get_token("keyword", "let")
            varname = self.get_token("identifier")[1]
            self.get_token("op", "=")
            value = self.parse_expression()
            return uast.Let(varname, value)

        if self.token_iter.peek() == ("keyword", "return"):
            self.get_token("keyword", "return")
            if self.token_iter.peek() == ("op", "\n"):
                return uast.Return(None)
            return uast.Return(self.parse_expression())

        if self.token_iter.peek() == ("keyword", "pass"):
            self.get_token("keyword", "pass")
            return uast.Pass()

        raise ValueError(self.token_iter.peek())

    def parse_statement(self) -> uast.Statement:
        if self.token_iter.peek() == ("keyword", "if"):
            self.get_token("keyword", "if")
            condition = self.parse_expression()
            body = self.parse_block(self.parse_statement)
            ifs = [(condition, body)]

            while self.token_iter.peek() == ("keyword", "elif"):
                self.get_token("keyword", "elif")
                condition = self.parse_expression()
                body = self.parse_block(self.parse_statement)
                ifs.append((condition, body))

            if self.token_iter.peek() == ("keyword", "else"):
                self.get_token("keyword", "else")
                else_body = self.parse_block(self.parse_statement)
            else:
                else_body = []

            return uast.If(ifs, else_body)

        if self.token_iter.peek() in {
            ("keyword", "let"),
            ("keyword", "return"),
            ("keyword", "pass"),
        }:
            result = self.parse_oneline_ish_statement()
            self.get_token("op", "\n")
            return result

        expr = self.parse_expression()
        if isinstance(expr, uast.GetVar) and self.token_iter.peek(None) == ("op", "="):
            self.get_token("op", "=")
            value = self.parse_expression()
            self.get_token("op", "\n")
            return uast.Assign(expr.varname, value)

        assert isinstance(expr, uast.Call), expr
        self.get_token("op", "\n")
        return expr

    def parse_type(self) -> str:
        return self.get_token("identifier")[1]

    def parse_funcdef_arg(self) -> Tuple[str, str]:
        type_name = self.parse_type()
        arg_name = self.get_token("identifier")[1]
        return (type_name, arg_name)

    def parse_function_or_method(self) -> uast.FuncDef:
        name = self.get_token("identifier")[1]
        args = self.parse_commasep_in_parens(self.parse_funcdef_arg)

        self.get_token("op", "->")
        if self.token_iter.peek() == ("keyword", "void"):
            returntype = None
            self.get_token("keyword", "void")
        else:
            returntype = self.parse_type()

        return uast.FuncDef(
            name, args, returntype, self.parse_block(self.parse_statement)
        )

    def parse_method(self) -> uast.FuncDef:
        self.get_token("keyword", "meth")
        return self.parse_function_or_method()

    def parse_toplevel(self) -> uast.ToplevelStatement:
        if self.token_iter.peek() == ("keyword", "func"):
            self.get_token("keyword", "func")
            return self.parse_function_or_method()

        if self.token_iter.peek() == ("keyword", "class"):
            self.get_token("keyword", "class")
            name = self.get_token("identifier")[1]
            args = self.parse_commasep_in_parens(self.parse_funcdef_arg)
            if self.token_iter.peek(None) == ("begin_block", ":"):
                body = self.parse_block(self.parse_method)
            else:
                body = []
                self.get_token("op", "\n")
            return uast.ClassDef(name, args, body)

        raise NotImplementedError(self.token_iter.peek())


def parse_file(tokens: Iterable[Tuple[str, str]]) -> List[uast.ToplevelStatement]:
    token_iter = more_itertools.peekable(tokens)
    parser = _Parser(token_iter)
    result = []
    while token_iter:
        result.append(parser.parse_toplevel())
    return result
