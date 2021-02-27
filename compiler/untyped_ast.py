# This ast has strings representing types
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class Expression:
    pass


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
class IntConstant(Expression):
    value: int


@dataclass
class FloatConstant(Expression):
    value: str  # not converted to float in case python's float does something weird


@dataclass
class UnaryOperator(Expression):
    op: str
    obj: Expression


@dataclass
class BinaryOperator(Expression):
    lhs: Expression
    op: str
    rhs: Expression


@dataclass
class Constructor(Expression):
    type: str


@dataclass
class Call(Expression, Statement):
    func: Expression
    args: List[Expression]


@dataclass
class LetStatement(Statement):
    varname: str
    value: Expression


@dataclass
class ReturnStatement(Statement):
    value: Optional[Expression]


@dataclass
class PassStatement(Statement):
    pass


@dataclass
class ToplevelStatement:
    pass


@dataclass
class FuncDef(ToplevelStatement):
    name: str
    args: List[Tuple[str, str]]  # first type, then name
    returntype: Optional[str]
    body: List[Statement]


@dataclass
class ClassDef(ToplevelStatement):
    name: str
    members: List[Tuple[str, str]]
    body: List[FuncDef]
