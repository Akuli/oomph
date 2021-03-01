from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class Type:
    name: str
    generic: Optional[Type]


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
class StringConstant(Expression):
    value: str


# result of string formatting
@dataclass
class StringFormatJoin(Expression):
    parts: List[Expression]

    def __init__(self, parts: List[Expression]):
        assert len(parts) >= 2
        self.parts = parts


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
    type: Type


@dataclass
class Call(Expression, Statement):
    func: Expression
    args: List[Expression]


@dataclass
class Let(Statement):
    varname: str
    value: Expression


@dataclass
class Assign(Statement):
    varname: str
    value: Expression


@dataclass
class Pass(Statement):
    pass


@dataclass
class Continue(Statement):
    pass


@dataclass
class Break(Statement):
    pass


@dataclass
class Return(Statement):
    value: Optional[Expression]


@dataclass
class If(Statement):
    ifs_and_elifs: List[Tuple[Expression, List[Statement]]]  # never empty list
    else_block: List[Statement]


# for init; cond; incr:
#    body
@dataclass
class Loop(Statement):
    init: Optional[Statement]
    cond: Optional[Expression]
    incr: Optional[Statement]
    body: List[Statement]


@dataclass
class ToplevelStatement:
    pass


@dataclass
class FuncDef(ToplevelStatement):
    name: str
    args: List[Tuple[Type, str]]
    returntype: Optional[Type]
    body: List[Statement]


@dataclass
class ClassDef(ToplevelStatement):
    type: Type
    members: List[Tuple[Type, str]]
    body: List[FuncDef]
