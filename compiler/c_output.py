# TODO: separate type checking and c output
from typing import Callable, Dict, Iterable, List, Optional, Tuple, TypeVar

from compiler.parser import (INT, Call, Expression, ExpressionStatement,
                             FuncDef, FunctionType, GetVar, IntConstant,
                             LetStatement, Statement, Type)


def _find_type(var_types: Dict[str, Type], ast: Expression) -> Type:
    if isinstance(ast, IntConstant):
        return INT
    if isinstance(ast, Call):
        functype = _find_type(var_types, ast.func)
        assert isinstance(functype, FunctionType)
        assert functype.returntype is not None
        return functype.returntype
    if isinstance(ast, GetVar):
        return var_types[ast.varname]
    raise NotImplementedError(ast)


_T = TypeVar('_T')


def _emit_commasep(items: Iterable[_T], callback: Callable[[_T], object]) -> None:
    first = True
    for item in items:
        if not first:
            print(',', end=' ')
        first = False
        callback(item)


def _emit_expression(var_types: Dict[str, Type], ast: Expression) -> Type:
    if isinstance(ast, IntConstant):
        assert -(2**63) <= ast.value < 2**63
        print(f'((int64_t){ast.value}LL)', end='')
        return INT
    elif isinstance(ast, Call):
        print('(', end='')
        functype = _emit_expression(var_types, ast.func)
        assert isinstance(functype, FunctionType)
        assert len(ast.args) == len(functype.argtypes)
        for arg, argtype in zip(ast.args, functype.argtypes):
            assert _find_type(var_types, arg) == argtype
        print('(', end='')
        _emit_commasep(ast.args, (lambda arg: _emit_expression(var_types, arg)))
        print('))', end='')
        return functype
    elif isinstance(ast, GetVar):
        print('var_' + ast.varname, end='')
        return var_types[ast.varname]
    else:
        raise NotImplementedError(ast)


def _emit_type(the_type: Optional[Type]) -> None:
    if the_type is INT:
        print('int64_t', end=' ')
    elif the_type is None:
        print('void', end=' ')
    else:
        raise NotImplementedError(the_type)


def _emit_statement(var_types: Dict[str, Type], ast: Statement) -> None:
    if isinstance(ast, LetStatement):
        assert ast.varname not in var_types
        var_types[ast.varname] = _find_type(var_types, ast.value)
        _emit_type(var_types[ast.varname])
        print('var_' + ast.varname, '=', end='')
        _emit_expression(var_types, ast.value)
    elif isinstance(ast, ExpressionStatement):
        print('(void)', end='')
        _emit_expression(var_types, ast.expression)
    else:
        raise NotImplementedError(ast)
    print(';\n\t', end='')


def _emit_block(var_types: Dict[str, Type], body: List[Statement]) -> None:
    print('{\n\t', end='')
    for statement in body:
        _emit_statement(var_types, statement)
    print('\n}')


def _emit_arg_def(pair: Tuple[Type, str]) -> None:
    the_type, name = pair
    _emit_type(the_type)
    print('var_' + name, end='')


def emit_funcdef(var_types: Dict[str, Type], funcdef: FuncDef) -> None:
    var_types[funcdef.name] = funcdef.type
    _emit_type(funcdef.type.returntype)
    assert len(funcdef.type.argtypes) == len(funcdef.argnames)
    if funcdef.argnames:
        print(f'var_{funcdef.name}(', end='')
        _emit_commasep(zip(funcdef.type.argtypes, funcdef.argnames), _emit_arg_def)
        print(')')
    else:
        print(f'var_{funcdef.name}(void)')
    local_vars = var_types.copy()
    local_vars.update(zip(funcdef.argnames, funcdef.type.argtypes))
    _emit_block(local_vars, funcdef.body)
