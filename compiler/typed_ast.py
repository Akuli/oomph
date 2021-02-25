from dataclasses import dataclass
from typing import (TYPE_CHECKING, Any, Callable, Iterable, List, Optional,
                    Tuple, TypeVar)

from compiler.types import FunctionType, Type


@dataclass
class Expression:
    type: Type


@dataclass
class Statement:
    pass


@dataclass
class GetVar(Expression):
    varname: str


@dataclass
class IntConstant(Expression):
    value: int


@dataclass
class VoidCall(Statement):
    func: Expression
    args: List[Expression]


@dataclass
class ReturningCall(Expression, Statement):
    func: Expression
    args: List[Expression]


@dataclass
class LetStatement(Statement):
    varname: str
    value: Expression


@dataclass
class ToplevelStatement:
    pass


@dataclass
class FuncDef(ToplevelStatement):
    name: str
    type: FunctionType
    argnames: List[str]
    body: List[Statement]


@dataclass
class ClassDef(ToplevelStatement):
    name: str
    members: List[Tuple[Type, str]]


@dataclass
class DecRef(Statement):
    varname: str
