import pathlib
from typing import Iterator, List, Optional, Tuple, TypeVar

import more_itertools

from oomphmini import tokenizer
from oomphmini import untyped_ast as uast

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

    def parse_commasep_expressions_in_parens(self) -> List[uast.Expression]:
        self.get_token("op", "(")
        result = []
        if self.token_iter.peek() != ("op", ")"):
            result.append(self.parse_expression())
            while self.token_iter.peek() == ("op", ","):
                self.get_token("op", ",")
                result.append(self.parse_expression())
        self.get_token("op", ")")
        return result

    def tokenize_and_parse_expression(self, code: str) -> uast.Expression:
        parser = _Parser(tokenizer.tokenize(code))
        result = parser.parse_expression()
        parser.get_token("op", "\n")
        assert not parser.token_iter, parser.token_iter.peek()
        return result

    def do_string_formatting(self, string: str) -> uast.Expression:
        return uast.StringConstant(string.strip('"'))

    def parse_expression(self) -> uast.Expression:
        result: uast.Expression
        if self.token_iter.peek()[0] == "oneline_string":
            result = self.do_string_formatting(
                self.get_token("oneline_string")[1][1:-1]
            )
        elif self.token_iter.peek()[0] == "identifier":
            result = uast.GetVar(self.get_token("identifier")[1])
        else:
            raise NotImplementedError(self.token_iter.peek())

        while True:
            if self.token_iter.peek() == ("op", "("):
                result = uast.Call(result, self.parse_commasep_expressions_in_parens())
            else:
                return result

    def parse_block_of_statements(self) -> List[uast.Statement]:
        result = []
        self.get_token("begin_block", ":")
        while self.token_iter and self.token_iter.peek(None) != ("end_block", ""):
            result.append(self.parse_statement())
        self.get_token("end_block", "")
        return result

    def parse_statement(self) -> uast.Statement:
        expr = self.parse_expression()
        assert isinstance(expr, uast.Call), expr
        self.get_token("op", "\n")
        return expr

    def parse_function_or_method(self) -> uast.FuncDef:
        name = self.get_token("identifier")[1]
        self.get_token("op", "(")
        self.get_token("op", ")")
        return uast.FuncDef(name, [], None, self.parse_block_of_statements())

    def parse_toplevel(self) -> uast.ToplevelDeclaration:
        self.get_token("keyword", "export")
        self.get_token("keyword", "func")
        result = self.parse_function_or_method()
        return result


def parse_file(
    code: str, path: Optional[pathlib.Path], stdlib: Optional[pathlib.Path]
) -> List[uast.ToplevelDeclaration]:
    parser = _Parser(tokenizer.tokenize(code))

    result: List[uast.ToplevelDeclaration] = []
    while parser.token_iter:
        result.append(parser.parse_toplevel())

    return result
