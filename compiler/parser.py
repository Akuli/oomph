from typing import (TYPE_CHECKING, Any, Callable, Iterable, List, Optional,
                    Tuple, TypeVar)

import more_itertools

from compiler import untyped_ast as uast

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
        assert tokentype == required_type, (required_type, required_value, tokentype, value)
    if required_value is not None:
        assert value == required_value, (required_type, required_value, tokentype, value)
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


def _parse_expression(token_iter: _TokenIter) -> uast.Expression:
    result: uast.Expression
    if token_iter.peek()[0] == 'var':
        result = uast.GetVar(_get_token(token_iter, 'var')[1])
    elif token_iter.peek()[0] == 'int':
        result = uast.IntConstant(int(_get_token(token_iter, 'int')[1]))
    else:
        raise NotImplementedError(token_iter.peek())

    while token_iter.peek() == ('op', '('):
        result = uast.Call(result, _parse_commasep_in_parens(token_iter, _parse_expression))
    return result


def _parse_statement(token_iter: _TokenIter) -> uast.Statement:
    result: uast.Statement
    if token_iter.peek() == ('keyword', 'let'):
        _get_token(token_iter, 'keyword', 'let')
        varname = _get_token(token_iter, 'var')[1]
        _get_token(token_iter, 'op', '=')
        result = uast.LetStatement(varname, _parse_expression(token_iter))
    else:
        call = _parse_expression(token_iter)
        assert isinstance(call, uast.Call)
        result = call

    _get_token(token_iter, 'op', '\n')
    return result


def _parse_block(token_iter: _TokenIter) -> List[uast.Statement]:
    _get_token(token_iter, 'begin_block', ':')
    result = []
    while token_iter and token_iter.peek(None) != ('end_block', ''):
        result.append(_parse_statement(token_iter))
    _get_token(token_iter, 'end_block', '')
    return result


def _parse_type(token_iter: _TokenIter) -> str:
    return _get_token(token_iter, 'var')[1]


def _parse_funcdef_arg(token_iter: _TokenIter) -> Tuple[str, str]:
    type_name = _parse_type(token_iter)
    arg_name = _get_token(token_iter, 'var')[1]
    return (type_name, arg_name)


def _parse_toplevel(token_iter: _TokenIter) -> uast.ToplevelStatement:
    if token_iter.peek() == ('keyword', 'func'):
        _get_token(token_iter, 'keyword', 'func')
        name = _get_token(token_iter, 'var')[1]
        args = _parse_commasep_in_parens(token_iter, _parse_funcdef_arg)
        _get_token(token_iter, 'op', '->')
        # TODO: accept return types
        _get_token(token_iter, 'keyword', 'void')
        return uast.FuncDef(
            name,
            args,
            None,
            _parse_block(token_iter),
        )
    if token_iter.peek() == ('keyword', 'class'):
        _get_token(token_iter, 'keyword', 'class')
        name = _get_token(token_iter, 'var')[1]
        args = _parse_commasep_in_parens(token_iter, _parse_funcdef_arg)
        _get_token(token_iter, 'op', '\n')
        return uast.ClassDef(name, args)
    raise NotImplementedError(token_iter.peek())


def parse_file(tokens: Iterable[Tuple[str, str]]) -> List[uast.ToplevelStatement]:
    token_iter = more_itertools.peekable(tokens)
    result = []
    while token_iter:
        result.append(_parse_toplevel(token_iter))
    return result
