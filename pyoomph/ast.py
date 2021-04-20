from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import List, Optional, Tuple, Union


@dataclass(eq=False)
class Type:
    pass


@dataclass(eq=False)
class AutoType(Type):
    pass


@dataclass(eq=False)
class GenericType(Type):
    name: str
    args: List[Type]


@dataclass(eq=False)
class NamedType(Type):
    name: str


@dataclass(eq=False)
class UnionType(Type):
    unioned: List[Type]


@dataclass(eq=False)
class Expression:
    pass


@dataclass(eq=False)
class Statement:
    pass


@dataclass(eq=False)
class Variable(Expression):
    name: str
    lineno: Optional[int] = None


@dataclass(eq=False)
class SetVar(Statement):
    var: Variable
    value: Expression


@dataclass(eq=False)
class GetAttribute(Expression):
    obj: Expression
    attribute: str


@dataclass(eq=False)
class SetAttribute(Statement):
    obj: Expression
    attribute: str
    value: Expression


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
class ListLiteral(Expression):
    content: List[Expression]


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
class As(Expression):
    expr: Expression
    type: Type
    as_not: bool


# Run statements and evaluate expression. Useful for list comprehensions.
@dataclass(eq=False)
class StatementsAndExpression(Expression):
    statements: List[Statement]
    expression: Expression


@dataclass(eq=False)
class Constructor(Expression):
    type: Type


@dataclass(eq=False)
class Call(Expression, Statement):
    func: Expression
    args: List[Expression]


@dataclass(eq=False)
class Let(Statement):
    var: Variable
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


# for init; cond; incr
@dataclass(eq=False)
class ForLoopHeader:
    init: List[Statement]
    cond: Optional[Expression]
    incr: List[Statement]


@dataclass(eq=False)
class ForeachLoopHeader:
    var: Variable
    list: Expression


@dataclass(eq=False)
class Loop(Statement):
    loop_header: Union[ForLoopHeader, ForeachLoopHeader]
    body: List[Statement]


@dataclass(eq=False)
class ListComprehension(Expression):
    loop_header: Union[ForLoopHeader, ForeachLoopHeader]
    value: Expression


@dataclass(eq=False)
class Case:
    # None means 'case *'
    type_and_var: Optional[Tuple[Type, Variable]]
    body: List[Statement]


@dataclass(eq=False)
class Switch(Statement):
    union_obj: Expression
    cases: List[Case]


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
    args: List[Tuple[Type, Variable]]
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
class TypeDef(ToplevelDeclaration):
    name: str
    type: Type
