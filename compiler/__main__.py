import re

import more_itertools


TOKEN_REGEX = (
    r'(?P<keyword>\blet\b|\bfunc\b|\bvoid\b)|'
    r'(?P<var>[A-Za-z_][A-Za-z0-9_]*)|'
    r'(?P<int>[1-9][0-9]*|0)|'
    r'(?P<op>[=+(),{}\n]|->)|'
    r'(?P<ignore> |#.*)|'
    r'(?P<error>.)'
)


def tokenize(code):
    if not code.endswith('\n'):
        code += '\n'

    for match in re.finditer(TOKEN_REGEX, code):
        tokentype = match.lastgroup
        value = match.group()
        assert tokentype != 'error', value
        if tokentype != 'ignore':
            yield (tokentype, match.group())
    yield ('end', '')


def clean_newlines(tokens):
    previous_value = None
    for tokentype, value in tokens:
        # Skip newline in beginning of file and double newlines
        if value != '\n' or (previous_value is not None and previous_value != '\n'):
            yield (tokentype, value)
        previous_value = value


def get_token(token_iter, required_type=None, required_value=None):
    tokentype, value = next(token_iter)
    if required_type is not None:
        assert tokentype == required_type, (tokentype, required_type)
    if required_value is not None:
        assert value == required_value, (value, required_value)
    return (tokentype, value)


def parse_commasep_in_parens(token_iter, content_callback):
    get_token(token_iter, 'op', '(')
    result = []
    if token_iter.peek() != ('op', ')'):
        result.append(content_callback(token_iter))
        while token_iter.peek() == ('op', ','):
            get_token(token_iter, 'op', ',')
            result.append(content_callback(token_iter))
    get_token(token_iter, 'op', ')')
    return result


def parse_expression(token_iter):
    if token_iter.peek()[0] == 'var':
        result = get_token(token_iter, 'var')
    elif token_iter.peek()[0] == 'int':
        result = ('int', int(get_token(token_iter, 'int')[1]))
    else:
        raise NotImplementedError(token_iter.peek())

    while token_iter.peek() == ('op', '('):
        result = ('call', result, parse_commasep_in_parens(token_iter, parse_expression))
    return result


def parse_statement(token_iter):
    if token_iter.peek() == ('keyword', 'let'):
        get_token(token_iter, 'keyword', 'let')
        varname = get_token(token_iter, 'var')[1]
        get_token(token_iter, 'op', '=')
        result = ('let', varname, parse_expression(token_iter))
    else:
        result = parse_expression(token_iter)

    get_token(token_iter, 'op', '\n')
    return result


def parse_block(token_iter):
    get_token(token_iter, 'op', '{')
    get_token(token_iter, 'op', '\n')
    result = []
    while token_iter.peek() != ('op', '}'):
        result.append(parse_statement(token_iter))
    get_token(token_iter, 'op', '}')
    get_token(token_iter, 'op', '\n')
    return result


def parse_type(token_iter):
    if token_iter.peek() == ('var', 'int'):
        get_token(token_iter, 'var', 'int')
        return 'int'
    raise NotImplementedError(token_iter.peek())


def parse_arg(token_iter):
    the_type = parse_type(token_iter)
    name = get_token(token_iter, 'var')[1]
    return (the_type, name)


def parse_toplevel(token_iter):
    if token_iter.peek() == ('keyword', 'func'):
        get_token(token_iter, 'keyword', 'func')
        name = get_token(token_iter, 'var')[1]
        args = parse_commasep_in_parens(token_iter, parse_arg)
        get_token(token_iter, 'op', '->')
        # TODO: accept return types
        get_token(token_iter, 'keyword', 'void')
        return ('func', name, args, None, parse_block(token_iter))
    raise NotImplementedError(token_iter.peek())


def find_type(var_types, ast):
    if ast[0] == 'int':
        return 'int'
    if ast[0] == 'call':
        literally_func, arg_types, returntype = find_type(var_types, ast[1])
        assert literally_func == 'func'
        assert returntype is not None
        return returntype
    if ast[0] == 'var':
        return var_types[ast[1]]
    raise NotImplementedError(ast)


def emit_commasep(items, callback):
    first = True
    for item in items:
        if not first:
            print(',', end=' ')
        first = False
        callback(item)


def emit_expression(var_types, ast):
    if ast[0] == 'int':
        assert -(2**63) <= ast[1] < 2**63
        print(f'((int64_t){ast[1]}LL)', end='')
        return 'int'
    elif ast[0] == 'call':
        print('(', end='')
        func, args = ast[1:]
        functype = emit_expression(var_types, func)
        assert functype[0] == 'func', functype
        argtypes, returntype = functype[1:]
        assert len(args) == len(argtypes)
        for arg, argtype in zip(args, argtypes):
            assert find_type(var_types, arg) == argtype
        print('(', end='')
        emit_commasep(args, (lambda arg: emit_expression(var_types, arg)))
        print('))', end='')
        return ('func', argtypes, returntype)
    elif ast[0] == 'var':
        print('var_' + ast[1], end='')
        return var_types[ast[1]]
    else:
        raise NotImplementedError(ast)


def emit_type(the_type):
    if the_type == 'int':
        print('int64_t', end=' ')
    elif the_type is None:
        print('void', end=' ')
    else:
        raise NotImplementedError(the_type)


def emit_statement(var_types, ast):
    if ast[0] == 'let':
        literally_let, varname, value = ast
        assert varname not in var_types
        var_types[varname] = find_type(var_types, value)
        emit_type(var_types[varname])
        print('var_' + varname, '=', end='')
        emit_expression(var_types, value)
    else:
        print('(void)', end='')
        emit_expression(var_types, ast)
    print(';\n\t', end='')


def emit_block(var_types, body):
    print('{\n\t', end='')
    for statement in body:
        emit_statement(var_types, statement)
    print('\n}')


def emit_arg_def(pair):
    the_type, name = pair
    emit_type(the_type)
    print('var_' + name, end='')


def emit_toplevel(var_types, toplevel):
    if toplevel[0] == 'func':
        name, args, returntype, body = toplevel[1:]
        var_types[name] = ('func', [the_type for the_type, name in args], returntype)
        emit_type(returntype)
        if args:
            print(f'var_{name}(', end='')
            emit_commasep(args, emit_arg_def)
            print(')')
        else:
            print(f'var_{name}(void)')
        local_vars = var_types.copy()
        local_vars.update({arg: typ for typ, arg in args})
        emit_block(local_vars, body)
    else:
        raise NotImplementedError(toplevel)


def main():
    print('#include <stdint.h>')
    print('#include <stdio.h>')
    print(r'void var_print_int(int64_t x){ printf("%lld\n", (long long)x); }')
    print(r'int64_t var_add(int64_t x, int64_t y){ return x+y; }')

    code = '''
func foo(int x) -> void {
    print_int(x)
}

func main() -> void {
    foo(12345)
    let x = add(1, 2)
    print_int(x)
    print_int(add(1, 2))
}
'''
    token_iter = more_itertools.peekable(clean_newlines(tokenize(code)))
    var_types = {'add': ('func', ['int', 'int'], 'int'), 'print_int': ('func', ['int'], None)}
    while token_iter.peek() != ('end', ''):
        emit_toplevel(var_types, parse_toplevel(token_iter))
    print('int main(void) { var_main(); return 0; }')


main()
