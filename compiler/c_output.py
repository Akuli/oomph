from typing import Callable, Iterable, List, Optional, Tuple, TypeVar

import compiler.typed_ast as tast
from compiler.types import Type, INT, ClassType

_T = TypeVar('_T')


def _emit_commasep(items: Iterable[_T], callback: Callable[[_T], object]) -> None:
    first = True
    for item in items:
        if not first:
            print(',', end=' ')
        first = False
        callback(item)


def _emit_expression(ast: tast.Expression) -> None:
    if isinstance(ast, tast.IntConstant):
        print(f'((int64_t){ast.value}LL)', end='')
    elif isinstance(ast, tast.Call):
        print('(', end='')
        _emit_expression(ast.func)
        print('(', end='')
        _emit_commasep(ast.args, (lambda arg: _emit_expression(arg)))
        print('))', end='')
    elif isinstance(ast, tast.GetVar):
        print('var_' + ast.varname, end='')
    else:
        raise NotImplementedError(ast)


def _emit_type(the_type: Optional[tast.Type]) -> None:
    if the_type is INT:
        print('int64_t', end=' ')
    elif isinstance(the_type, ClassType):
        print(f'struct class_{the_type.name} *', end='')
    elif the_type is None:
        print('void', end=' ')
    else:
        raise NotImplementedError(the_type)


def _emit_statement(ast: tast.Statement) -> None:
    if isinstance(ast, tast.LetStatement):
        _emit_type(ast.value.type)
        print(f'var_{ast.varname} =', end=' ')
        _emit_expression(ast.value)
    elif isinstance(ast, tast.Call):
        _emit_expression(ast)
    else:
        raise NotImplementedError(ast)
    print(';\n\t', end='')


def _emit_block(body: List[tast.Statement]) -> None:
    print('{\n\t', end='')
    for statement in body:
        _emit_statement(statement)
    print('\n}')


def _emit_arg_def(pair: Tuple[Type, str]) -> None:
    the_type, name = pair
    _emit_type(the_type)
    print('var_' + name, end='')


def emit_toplevel_statement(top_statement: tast.ToplevelStatement) -> None:
    if isinstance(top_statement, tast.FuncDef):
        _emit_type(top_statement.type.returntype)
        if top_statement.argnames:
            print(f'var_{top_statement.name}(', end='')
            _emit_commasep(zip(top_statement.type.argtypes, top_statement.argnames), _emit_arg_def)
            print(')')
        else:
            print(f'var_{top_statement.name}(void)')
        _emit_block(top_statement.body)
    elif isinstance(top_statement, tast.ClassDef):
        print('struct class_%s {' % top_statement.name, end='\n\t')
        for the_type, name in top_statement.members:
            _emit_type(the_type)
            print(name + ';', end='\n\t')
        print('\n};')
    else:
        raise NotImplementedError(top_statement)
