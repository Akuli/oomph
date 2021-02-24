def _find_type(var_types, ast):
    if ast[0] == 'int':
        return 'int'
    if ast[0] == 'call':
        literally_func, arg_types, returntype = _find_type(var_types, ast[1])
        assert literally_func == 'func'
        assert returntype is not None
        return returntype
    if ast[0] == 'var':
        return var_types[ast[1]]
    raise NotImplementedError(ast)


def _emit_commasep(items, callback):
    first = True
    for item in items:
        if not first:
            print(',', end=' ')
        first = False
        callback(item)


def _emit_expression(var_types, ast):
    if ast[0] == 'int':
        assert -(2**63) <= ast[1] < 2**63
        print(f'((int64_t){ast[1]}LL)', end='')
        return 'int'
    elif ast[0] == 'call':
        print('(', end='')
        func, args = ast[1:]
        functype = _emit_expression(var_types, func)
        assert functype[0] == 'func', functype
        argtypes, returntype = functype[1:]
        assert len(args) == len(argtypes)
        for arg, argtype in zip(args, argtypes):
            assert _find_type(var_types, arg) == argtype
        print('(', end='')
        _emit_commasep(args, (lambda arg: _emit_expression(var_types, arg)))
        print('))', end='')
        return ('func', argtypes, returntype)
    elif ast[0] == 'var':
        print('var_' + ast[1], end='')
        return var_types[ast[1]]
    else:
        raise NotImplementedError(ast)


def _emit_type(the_type):
    if the_type == 'int':
        print('int64_t', end=' ')
    elif the_type is None:
        print('void', end=' ')
    else:
        raise NotImplementedError(the_type)


def _emit_statement(var_types, ast):
    if ast[0] == 'let':
        literally_let, varname, value = ast
        assert varname not in var_types
        var_types[varname] = _find_type(var_types, value)
        _emit_type(var_types[varname])
        print('var_' + varname, '=', end='')
        _emit_expression(var_types, value)
    else:
        print('(void)', end='')
        _emit_expression(var_types, ast)
    print(';\n\t', end='')


def _emit_block(var_types, body):
    print('{\n\t', end='')
    for statement in body:
        _emit_statement(var_types, statement)
    print('\n}')


def _emit_arg_def(pair):
    the_type, name = pair
    _emit_type(the_type)
    print('var_' + name, end='')


def emit_toplevel(var_types, toplevel):
    if toplevel[0] == 'func':
        name, args, returntype, body = toplevel[1:]
        var_types[name] = ('func', [the_type for the_type, name in args], returntype)
        _emit_type(returntype)
        if args:
            print(f'var_{name}(', end='')
            _emit_commasep(args, _emit_arg_def)
            print(')')
        else:
            print(f'var_{name}(void)')
        local_vars = var_types.copy()
        local_vars.update({arg: typ for typ, arg in args})
        _emit_block(local_vars, body)
    else:
        raise NotImplementedError(toplevel)
