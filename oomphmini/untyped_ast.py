from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass(eq=False)
class Type:
    name: str


@dataclass(eq=False)
class Expression:
    pass


@dataclass(eq=False)
class Statement:
    pass


@dataclass(eq=False)
class GetVar(Expression):
    varname: str
    lineno: Optional[int] = None


@dataclass(eq=False)
class StringConstant(Expression):
    value: str


@dataclass(eq=False)
class Call(Expression, Statement):
    func: Expression
    args: List[Expression]


@dataclass(eq=False)
class ToplevelDeclaration:
    pass


@dataclass(eq=False)
class FuncDef(ToplevelDeclaration):
    name: str
    args: List[Tuple[Type, str]]
    returntype: Optional[Type]
    body: List[Statement]
