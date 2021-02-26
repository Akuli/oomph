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
class GetAttribute(Expression):
    obj: Expression
    attribute: str


@dataclass
class GetMethod(Expression):
    obj: Expression
    name: str


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
class ReturnStatement(Statement):
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
    refnames: List[str]


@dataclass
class ClassDef(ToplevelStatement):
    type: ClassType
    body: List[FuncDef]


@dataclass
class SetRef(Expression):
    refname: str
    value: Expression


@dataclass
class DecRefObject(Statement):
    value: Expression


@dataclass
class Constructor(Expression):
    class_to_construct: ClassType
