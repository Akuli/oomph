import more_itertools


def _get_token(token_iter, required_type=None, required_value=None):
    tokentype, value = next(token_iter)
    if required_type is not None:
        assert tokentype == required_type, (tokentype, required_type)
    if required_value is not None:
        assert value == required_value, (value, required_value)
    return (tokentype, value)


def _parse_commasep_in_parens(token_iter, content_callback):
    _get_token(token_iter, 'op', '(')
    result = []
    if token_iter.peek() != ('op', ')'):
        result.append(content_callback(token_iter))
        while token_iter.peek() == ('op', ','):
            _get_token(token_iter, 'op', ',')
            result.append(content_callback(token_iter))
    _get_token(token_iter, 'op', ')')
    return result


def _parse_expression(token_iter):
    if token_iter.peek()[0] == 'var':
        result = _get_token(token_iter, 'var')
    elif token_iter.peek()[0] == 'int':
        result = ('int', int(_get_token(token_iter, 'int')[1]))
    else:
        raise NotImplementedError(token_iter.peek())

    while token_iter.peek() == ('op', '('):
        result = ('call', result, _parse_commasep_in_parens(token_iter, _parse_expression))
    return result


def _parse_statement(token_iter):
    if token_iter.peek() == ('keyword', 'let'):
        _get_token(token_iter, 'keyword', 'let')
        varname = _get_token(token_iter, 'var')[1]
        _get_token(token_iter, 'op', '=')
        result = ('let', varname, _parse_expression(token_iter))
    else:
        result = _parse_expression(token_iter)

    _get_token(token_iter, 'op', '\n')
    return result


def _parse_block(token_iter):
    _get_token(token_iter, 'op', '{')
    _get_token(token_iter, 'op', '\n')
    result = []
    while token_iter.peek() != ('op', '}'):
        result.append(_parse_statement(token_iter))
    _get_token(token_iter, 'op', '}')
    _get_token(token_iter, 'op', '\n')
    return result


def _parse_type(token_iter):
    if token_iter.peek() == ('var', 'int'):
        _get_token(token_iter, 'var', 'int')
        return 'int'
    raise NotImplementedError(token_iter.peek())


def _parse_arg(token_iter):
    the_type = _parse_type(token_iter)
    name = _get_token(token_iter, 'var')[1]
    return (the_type, name)


def _parse_toplevel(token_iter):
    if token_iter.peek() == ('keyword', 'func'):
        _get_token(token_iter, 'keyword', 'func')
        name = _get_token(token_iter, 'var')[1]
        args = _parse_commasep_in_parens(token_iter, _parse_arg)
        _get_token(token_iter, 'op', '->')
        # TODO: accept return types
        _get_token(token_iter, 'keyword', 'void')
        return ('func', name, args, None, _parse_block(token_iter))
    raise NotImplementedError(token_iter.peek())


def parse_file(tokens):
    token_iter = more_itertools.peekable(tokens)
    while token_iter.peek() != ('end', ''):
        yield _parse_toplevel(token_iter)
