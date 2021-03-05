from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(eq=False)
class Type:
    name: str
    generic: Optional[Type]


@dataclass(eq=False)
class Expression:
    pass


@dataclass(eq=False)
class Statement:
    pass


@dataclass(eq=False)
class Null(Expression):
    type: Type


@dataclass(eq=False)
class GetVar(Expression):
    varname: str
    lineno: Optional[int] = None


@dataclass(eq=False)
class GetAttribute(Expression):
    obj: Expression
    attribute: str


@dataclass(eq=False)
class StringConstant(Expression):
    value: str


# result of string formatting
@dataclass(eq=False)
class StringFormatJoin(Expression):
    parts: List[Expression]

    def __init__(self, parts: List[Expression]):
        assert len(parts) >= 2
        self.parts = parts


@dataclass(eq=False)
class IntConstant(Expression):
    value: int


@dataclass(eq=False)
class FloatConstant(Expression):
    value: str  # not converted to float in case python's float does something weird


@dataclass(eq=False)
class UnaryOperator(Expression):
    op: str
    obj: Expression


@dataclass(eq=False)
class BinaryOperator(Expression):
    lhs: Expression
    op: str
    rhs: Expression


@dataclass(eq=False)
class Constructor(Expression):
    type: Type


@dataclass(eq=False)
class Call(Expression, Statement):
    func: Expression
    args: List[Expression]


@dataclass(eq=False)
class Let(Statement):
    varname: str
    value: Expression


@dataclass(eq=False)
class Assign(Statement):
    varname: str
    value: Expression


@dataclass(eq=False)
class Pass(Statement):
    pass


@dataclass(eq=False)
class Continue(Statement):
    pass


@dataclass(eq=False)
class Break(Statement):
    pass


@dataclass(eq=False)
class Return(Statement):
    value: Optional[Expression]


@dataclass(eq=False)
class If(Statement):
    ifs_and_elifs: List[Tuple[Expression, List[Statement]]]  # never empty list
    else_block: List[Statement]


# for init; cond; incr:
#    body
@dataclass(eq=False)
class Loop(Statement):
    init: Optional[Statement]
    cond: Optional[Expression]
    incr: Optional[Statement]
    body: List[Statement]


@dataclass(eq=False)
class Switch(Statement):
    varname: str
    cases: Dict[Type, List[Statement]]


@dataclass(eq=False)
class ToplevelDeclaration:
    pass


@dataclass(eq=False)
class Import(ToplevelDeclaration):
    path: pathlib.Path
    name: str


@dataclass(eq=False)
class FuncOrMethodDef(ToplevelDeclaration):
    name: str
    args: List[Tuple[Type, str]]
    returntype: Optional[Type]
    body: List[Statement]
    export: bool = False  # never true for methods


@dataclass(eq=False)
class ClassDef(ToplevelDeclaration):
    name: str
    members: List[Tuple[Type, str]]
    body: List[FuncOrMethodDef]
    export: bool


@dataclass(eq=False)
class UnionDef(ToplevelDeclaration):
    name: str
    type_members: List[Type]
