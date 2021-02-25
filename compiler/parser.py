from dataclasses import dataclass
from typing import (TYPE_CHECKING, Any, Callable, Iterable, List, Optional,
                    Tuple, TypeVar)

import more_itertools

from compiler.types import INT, FunctionType, Type

if TYPE_CHECKING:
    _TokenIter = more_itertools.peekable[Tuple[str, str]]
else:
    _TokenIter = Any
_T = TypeVar('_T')


def _get_token(
    token_iter: _TokenIter,
    required_type: Optional[str] = None,
    required_value: Optional[str] = None,
) -> Tuple[str, str]:
    tokentype, value = next(token_iter)
    if required_type is not None:
        assert tokentype == required_type, (tokentype, required_type)
    if required_value is not None:
        assert value == required_value, (value, required_value)
    return (tokentype, value)


def _parse_commasep_in_parens(token_iter: _TokenIter, content_callback: Callable[[_TokenIter], _T]) -> List[_T]:
    _get_token(token_iter, 'op', '(')
    result = []
    if token_iter.peek() != ('op', ')'):
        result.append(content_callback(token_iter))
        while token_iter.peek() == ('op', ','):
            _get_token(token_iter, 'op', ',')
            result.append(content_callback(token_iter))
    _get_token(token_iter, 'op', ')')
    return result


@dataclass
class Expression:
    pass


@dataclass
class GetVar(Expression):
    varname: str


@dataclass
class IntConstant(Expression):
    value: int


@dataclass
class Call(Expression):
    func: Expression
    args: List[Expression]


def _parse_expression(token_iter: _TokenIter) -> Expression:
    result: Expression
    if token_iter.peek()[0] == 'var':
        result = GetVar(_get_token(token_iter, 'var')[1])
    elif token_iter.peek()[0] == 'int':
        result = IntConstant(int(_get_token(token_iter, 'int')[1]))
    else:
        raise NotImplementedError(token_iter.peek())

    while token_iter.peek() == ('op', '('):
        result = Call(result, _parse_commasep_in_parens(token_iter, _parse_expression))
    return result


@dataclass
class Statement:
    pass


@dataclass
class LetStatement(Statement):
    varname: str
    value: Expression
    value_type: Optional[Type]


@dataclass
class ExpressionStatement(Statement):
    expression: Expression


def _parse_statement(token_iter: _TokenIter) -> Statement:
    result: Statement
    if token_iter.peek() == ('keyword', 'let'):
        _get_token(token_iter, 'keyword', 'let')
        varname = _get_token(token_iter, 'var')[1]
        _get_token(token_iter, 'op', '=')
        result = LetStatement(varname, _parse_expression(token_iter), None)
    else:
        result = ExpressionStatement(_parse_expression(token_iter))

    _get_token(token_iter, 'op', '\n')
    return result


def _parse_block(token_iter: _TokenIter) -> List[Statement]:
    _get_token(token_iter, 'op', '{')
    _get_token(token_iter, 'op', '\n')
    result = []
    while token_iter.peek() != ('op', '}'):
        result.append(_parse_statement(token_iter))
    _get_token(token_iter, 'op', '}')
    _get_token(token_iter, 'op', '\n')
    return result


def _parse_type(token_iter: _TokenIter) -> Type:
    if token_iter.peek() == ('var', 'int'):
        _get_token(token_iter, 'var', 'int')
        return INT
    raise NotImplementedError(token_iter.peek())


def _parse_funcdef_arg(token_iter: _TokenIter) -> Tuple[Type, str]:
    the_type = _parse_type(token_iter)
    name = _get_token(token_iter, 'var')[1]
    return (the_type, name)


@dataclass
class FuncDef:
    name: str
    type: FunctionType
    argnames: List[str]
    body: List[Statement]


def _parse_toplevel(token_iter: _TokenIter) -> FuncDef:
    if token_iter.peek() == ('keyword', 'func'):
        _get_token(token_iter, 'keyword', 'func')
        name = _get_token(token_iter, 'var')[1]
        args = _parse_commasep_in_parens(token_iter, _parse_funcdef_arg)
        _get_token(token_iter, 'op', '->')
        # TODO: accept return types
        _get_token(token_iter, 'keyword', 'void')
        return FuncDef(
            name,
            FunctionType([argtype for argtype, name in args], None),
            [name for argtype, name in args],
            _parse_block(token_iter),
        )
    raise NotImplementedError(token_iter.peek())


def parse_file(tokens: Iterable[Tuple[str, str]]) -> List[FuncDef]:
    token_iter = more_itertools.peekable(tokens)
    result = []
    while token_iter.peek() != ('end', ''):
        result.append(_parse_toplevel(token_iter))
    return result
