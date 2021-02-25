from dataclasses import dataclass
from typing import List

from compiler.types import ClassType, FunctionType, Type


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
    type: ClassType


@dataclass
class DeclareRef(Statement):
    refname: str


@dataclass
class NewRef(Statement):
    refname: str


@dataclass
class SetRef(Expression):
    refname: str
    value: Expression


@dataclass
class DecRef(Statement):
    refname: str


@dataclass
class DecRefObject(Statement):
    value: Expression


@dataclass
class Constructor(Expression):
    class_to_construct: ClassType
