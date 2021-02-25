from typing import Callable, Iterable, List, Optional, Tuple, TypeVar

from compiler.parser import (INT, Call, Expression, ExpressionStatement,
                             FuncDef, GetVar, IntConstant, LetStatement,
                             Statement, Type)

_T = TypeVar('_T')


def _emit_commasep(items: Iterable[_T], callback: Callable[[_T], object]) -> None:
    first = True
    for item in items:
        if not first:
            print(',', end=' ')
        first = False
        callback(item)


def _emit_expression(ast: Expression) -> Type:
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
    if the_type is INT:
        print('int64_t', end=' ')
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
    elif isinstance(ast, ExpressionStatement):
        print('(void)', end=' ')
        _emit_expression(ast.expression)
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


def emit_funcdef(funcdef: FuncDef) -> None:
    _emit_type(funcdef.type.returntype)
    if funcdef.argnames:
        print(f'var_{funcdef.name}(', end='')
        _emit_commasep(zip(funcdef.type.argtypes, funcdef.argnames), _emit_arg_def)
        print(')')
    else:
        print(f'var_{funcdef.name}(void)')
    _emit_block(funcdef.body)
