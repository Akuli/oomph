from typing import Callable, Iterable, List, Optional, Tuple, TypeVar

from compiler.parser import (Call, ClassDef, Expression, FuncDef, GetVar,
                             IntConstant, LetStatement, Statement,
                             ToplevelStatement)
from compiler.types import NamedType, Type

_T = TypeVar('_T')


def _emit_commasep(items: Iterable[_T], callback: Callable[[_T], object]) -> None:
    first = True
    for item in items:
        if not first:
            print(',', end=' ')
        first = False
        callback(item)


def _emit_expression(ast: Expression) -> None:
    if isinstance(ast, IntConstant):
        print(f'((int64_t){ast.value}LL)', end='')
    elif isinstance(ast, Call):
        print('(', end='')
        _emit_expression(ast.func)
        print('(', end='')
        _emit_commasep(ast.args, (lambda arg: _emit_expression(arg)))
        print('))', end='')
    elif isinstance(ast, GetVar):
        print('var_' + ast.varname, end='')
    else:
        raise NotImplementedError(ast)


def _emit_type(the_type: Optional[Type]) -> None:
    if isinstance(the_type, NamedType):
        if the_type.name == 'int':
            print('int64_t', end=' ')
        else:
            print(f'struct class_{the_type.name} *', end='')
    elif the_type is None:
        print('void', end=' ')
    else:
        raise NotImplementedError(the_type)


def _emit_statement(ast: Statement) -> None:
    if isinstance(ast, LetStatement):
        assert ast.value_type is not None
        _emit_type(ast.value_type)
        print(f'var_{ast.varname} =', end=' ')
        _emit_expression(ast.value)
    elif isinstance(ast, Call):
        _emit_expression(ast)
    else:
        raise NotImplementedError(ast)
    print(';\n\t', end='')


def _emit_block(body: List[Statement]) -> None:
    print('{\n\t', end='')
    for statement in body:
        _emit_statement(statement)
    print('\n}')


def _emit_arg_def(pair: Tuple[Type, str]) -> None:
    the_type, name = pair
    _emit_type(the_type)
    print('var_' + name, end='')


def emit_toplevel_statement(top_statement: ToplevelStatement) -> None:
    if isinstance(top_statement, FuncDef):
        _emit_type(top_statement.type.returntype)
        if top_statement.argnames:
            print(f'var_{top_statement.name}(', end='')
            _emit_commasep(zip(top_statement.type.argtypes, top_statement.argnames), _emit_arg_def)
            print(')')
        else:
            print(f'var_{top_statement.name}(void)')
        _emit_block(top_statement.body)
    elif isinstance(top_statement, ClassDef):
        print('struct class_%s {' % top_statement.name, end='\n\t')
        for the_type, name in top_statement.members:
            _emit_type(the_type)
            print(name + ';', end='\n\t')
        print('\n};')
    else:
        raise NotImplementedError(top_statement)
