from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Iterable,
    Iterator,
    List,
    Optional,
    Tuple,
    TypeVar,
    Union,
)

import more_itertools

from compiler import untyped_ast as uast

if TYPE_CHECKING:
    _TokenIter = more_itertools.peekable[Tuple[str, str]]
else:
    _TokenIter = Any
_T = TypeVar("_T")


def _get_token(
    token_iter: _TokenIter,
    required_type: Optional[str] = None,
    required_value: Optional[str] = None,
) -> Tuple[str, str]:
    tokentype, value = next(token_iter)
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


def _parse_commasep_in_parens(
    token_iter: _TokenIter, content_callback: Callable[[_TokenIter], _T]
) -> List[_T]:
    _get_token(token_iter, "op", "(")
    result = []
    if token_iter.peek() != ("op", ")"):
        result.append(content_callback(token_iter))
        while token_iter.peek() == ("op", ","):
            _get_token(token_iter, "op", ",")
            result.append(content_callback(token_iter))
    _get_token(token_iter, "op", ")")
    return result


def _parse_expression_without_operators(token_iter: _TokenIter) -> uast.Expression:
    result: uast.Expression
    if token_iter.peek()[0] == "var":
        result = uast.GetVar(_get_token(token_iter, "var")[1])
    elif token_iter.peek()[0] == "int":
        result = uast.IntConstant(int(_get_token(token_iter, "int")[1]))
    elif token_iter.peek()[0] == "float":
        result = uast.FloatConstant(_get_token(token_iter, "float")[1])
    elif token_iter.peek() == ("keyword", "new"):
        _get_token(token_iter, "keyword", "new")
        result = uast.Constructor(_parse_type(token_iter))
    elif token_iter.peek() == ("op", "("):
        _get_token(token_iter, "op", "(")
        result = _parse_expression(token_iter)
        _get_token(token_iter, "op", ")")
    else:
        raise NotImplementedError(token_iter.peek())

    while True:
        if token_iter.peek() == ("op", "("):
            result = uast.Call(
                result, _parse_commasep_in_parens(token_iter, _parse_expression)
            )
        elif token_iter.peek() == ("op", "."):
            _get_token(token_iter, "op", ".")
            result = uast.GetAttribute(result, _get_token(token_iter, "var")[1])
        else:
            return result


def _get_unary_operators(token_iter: _TokenIter) -> Iterator[Tuple[int, str]]:
    while token_iter.peek() in {("keyword", "not"), ("op", "-")}:
        yield (1, _get_token(token_iter)[1])


def _parse_expression(token_iter: _TokenIter) -> uast.Expression:
    magic_list: List[Union[Tuple[int, str], uast.Expression]] = []
    magic_list.extend(_get_unary_operators(token_iter))
    magic_list.append(_parse_expression_without_operators(token_iter))

    while token_iter.peek() in {
        ("op", "+"),
        ("op", "-"),
        ("op", "*"),
        ("op", "/"),
        ("keyword", "and"),
        ("keyword", "or"),
    }:
        magic_list.append((2, _get_token(token_iter)[1]))
        magic_list.extend(_get_unary_operators(token_iter))
        magic_list.append(_parse_expression_without_operators(token_iter))

    # A common python beginner mistake is writing "a and b or c", thinking it
    # means "a and (b or c)"
    assert not ("and" in magic_list and "or" in magic_list)

    # Disallow a--b and --a, require a-(-b) or -(-a)
    assert not any(
        first in [(1, "-"), (2, "-")] and second == (1, "-")
        for first, second in zip(magic_list, magic_list[1:])
    )

    # each operator of a group is considered to have same precedence
    for op_group in [
        [(2, "*"), (2, "/")],
        [(2, "+"), (2, "-"), (1, "-")],
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
                magic_list[where : where + 2] = [uast.UnaryOperator(op_string, operand)]
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


def _parse_statement(token_iter: _TokenIter) -> Optional[uast.Statement]:
    result: uast.Statement
    if token_iter.peek() == ("keyword", "let"):
        _get_token(token_iter, "keyword", "let")
        varname = _get_token(token_iter, "var")[1]
        _get_token(token_iter, "op", "=")
        result = uast.LetStatement(varname, _parse_expression(token_iter))
    elif token_iter.peek() == ("keyword", "return"):
        _get_token(token_iter, "keyword", "return")
        if token_iter.peek() == ("op", "\n"):
            result = uast.ReturnStatement(None)
        else:
            result = uast.ReturnStatement(_parse_expression(token_iter))
    elif token_iter.peek() == ("keyword", "pass"):
        _get_token(token_iter, "keyword", "pass")
        result = uast.PassStatement()
    else:
        call = _parse_expression(token_iter)
        assert isinstance(call, uast.Call), call
        result = call

    _get_token(token_iter, "op", "\n")
    return result


def _parse_block(
    token_iter: _TokenIter, callback: Callable[[_TokenIter], _T]
) -> List[_T]:
    _get_token(token_iter, "begin_block", ":")
    result = []
    while token_iter and token_iter.peek(None) != ("end_block", ""):
        result.append(callback(token_iter))
    _get_token(token_iter, "end_block", "")
    return result


def _parse_type(token_iter: _TokenIter) -> str:
    return _get_token(token_iter, "var")[1]


def _parse_funcdef_arg(token_iter: _TokenIter) -> Tuple[str, str]:
    type_name = _parse_type(token_iter)
    arg_name = _get_token(token_iter, "var")[1]
    return (type_name, arg_name)


def _parse_function_or_method(token_iter: _TokenIter) -> uast.FuncDef:
    name = _get_token(token_iter, "var")[1]
    args = _parse_commasep_in_parens(token_iter, _parse_funcdef_arg)

    _get_token(token_iter, "op", "->")
    if token_iter.peek() == ("keyword", "void"):
        returntype = None
        _get_token(token_iter, "keyword", "void")
    else:
        returntype = _parse_type(token_iter)

    return uast.FuncDef(
        name,
        args,
        returntype,
        [
            item
            for item in _parse_block(token_iter, _parse_statement)
            if item is not None
        ],
    )


def _parse_method(token_iter: _TokenIter) -> uast.FuncDef:
    _get_token(token_iter, "keyword", "meth")
    return _parse_function_or_method(token_iter)


def _parse_toplevel(token_iter: _TokenIter) -> uast.ToplevelStatement:
    if token_iter.peek() == ("keyword", "func"):
        _get_token(token_iter, "keyword", "func")
        return _parse_function_or_method(token_iter)

    if token_iter.peek() == ("keyword", "class"):
        _get_token(token_iter, "keyword", "class")
        name = _get_token(token_iter, "var")[1]
        args = _parse_commasep_in_parens(token_iter, _parse_funcdef_arg)
        if token_iter.peek(None) == ("begin_block", ":"):
            body = _parse_block(token_iter, _parse_method)
        else:
            body = []
            _get_token(token_iter, "op", "\n")
        return uast.ClassDef(name, args, body)

    raise NotImplementedError(token_iter.peek())


def parse_file(tokens: Iterable[Tuple[str, str]]) -> List[uast.ToplevelStatement]:
    token_iter = more_itertools.peekable(tokens)
    result = []
    while token_iter:
        result.append(_parse_toplevel(token_iter))
    return result
