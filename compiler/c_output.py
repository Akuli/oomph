from functools import partial
from typing import Callable, Iterable, List, Optional, Tuple, TypeVar, Union, IO

import compiler.typed_ast as tast
from compiler.types import INT, ClassType, Type

_T = TypeVar('_T')


def _emit_commasep(file: IO[str], items: Iterable[_T], callback: Callable[[_T], object]) -> None:
    first = True
    for item in items:
        if not first:
            file.write(',')
        first = False
        callback(item)


def _emit_call(file: IO[str], ast: Union[tast.ReturningCall, tast.VoidCall]) -> None:
    file.write('(')
    _emit_expression(file, ast.func)
    file.write('(')
    _emit_commasep(file, ast.args, (lambda arg: _emit_expression(file, arg)))
    file.write('))')


def _emit_expression(file: IO[str], ast: tast.Expression) -> None:
    if isinstance(ast, tast.IntConstant):
        file.write(f'((int64_t){ast.value}LL)')
    elif isinstance(ast, tast.ReturningCall):
        _emit_call(file, ast)
    elif isinstance(ast, tast.GetVar):
        file.write('var_' + ast.varname)
    elif isinstance(ast, tast.Constructor):
        file.write('ctor_' + ast.class_to_construct.name)
    elif isinstance(ast, tast.SetRef):
        file.write(f'({ast.refname} = ')
        _emit_expression(file, ast.value)
        file.write(')')
    elif isinstance(ast, tast.GetAttribute):
        file.write('((')
        _emit_expression(file, ast.obj)
        file.write(f')->memb_{ast.attribute})')
    else:
        raise NotImplementedError(ast)


def _emit_statement(file: IO[str], ast: tast.Statement) -> None:
    if isinstance(ast, tast.LetStatement):
        _emit_type(file, ast.value.type)
        file.write(f'var_{ast.varname} = ')
        _emit_expression(file, ast.value)
    elif isinstance(ast, (tast.ReturningCall, tast.VoidCall)):
        _emit_call(file, ast)
    elif isinstance(ast, tast.NewRef):
        file.write(f'void *{ast.refname} = NULL')
    elif isinstance(ast, tast.DecRef):
        file.write(f'if ({ast.refname}) decref({ast.refname})')
    elif isinstance(ast, tast.DecRefObject):
        file.write('decref(')
        _emit_expression(file, ast.value)
        file.write(')')
    else:
        raise NotImplementedError(ast)
    file.write(';\n\t')


def _emit_type(file: IO[str], the_type: Optional[Type]) -> None:
    if the_type is INT:
        file.write('int64_t ')
    elif isinstance(the_type, ClassType):
        file.write(f'struct class_{the_type.name} *')
    elif the_type is None:
        file.write('void ')
    else:
        raise NotImplementedError(the_type)


def _emit_block(file: IO[str], body: List[tast.Statement]) -> None:
    file.write('{\n\t')
    for statement in body:
        _emit_statement(file, statement)
    file.write('\n}\n')


def _emit_arg_def(file: IO[str], pair: Tuple[Type, str]) -> None:
    the_type, name = pair
    _emit_type(file, the_type)
    file.write('var_' + name)


def emit_toplevel_statement(file: IO[str], top_statement: tast.ToplevelStatement) -> None:
    if isinstance(top_statement, tast.FuncDef):
        _emit_type(file, top_statement.type.returntype)
        if top_statement.argnames:
            file.write(f'var_{top_statement.name}(')
            _emit_commasep(file, zip(top_statement.type.argtypes, top_statement.argnames), partial(_emit_arg_def, file))
            file.write(')')
        else:
            file.write(f'var_{top_statement.name}(void)')
        _emit_block(file, top_statement.body)

    elif isinstance(top_statement, tast.ClassDef):
        # struct
        file.write('struct class_%s {\n' % top_statement.type.name)
        file.write('\tREFCOUNT_HEADER\n\t')
        for the_type, name in top_statement.type.members:
            _emit_type(file, the_type)
            file.write('memb_' + name + ';\n\t')
        file.write('\n};\n')

        # constructor
        _emit_type(file, top_statement.type)
        file.write(f'ctor_{top_statement.type.name}(')
        _emit_commasep(file, top_statement.type.members, partial(_emit_arg_def, file))
        file.write(') {\n\t')
        _emit_type(file, top_statement.type)
        file.write('obj = malloc(sizeof(*obj));\n')
        file.write('\tobj->refcount = 1;\n')
        for the_type, name in top_statement.type.members:
            file.write(f'\tobj->memb_{name} = var_{name};\n')
        file.write('\treturn obj;\n}\n')

    else:
        raise NotImplementedError(top_statement)
