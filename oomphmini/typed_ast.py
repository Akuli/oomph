from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import List, Optional, Tuple, Union

from oomphmini.types import STRING, FunctionType, Type


@dataclass(eq=False)
class Expression:
    type: Type


@dataclass(eq=False)
class Statement:
    pass


@dataclass(eq=False)
class Variable:
    name: str
    type: Type


# There can be different local variables with same name, even in the same
# function. They are represented as different instances of this class.
@dataclass(eq=False)
class LocalVariable(Variable):
    pass


@dataclass(eq=False)
class ExportVariable(Variable):
    pass


@dataclass(eq=False)
class BuiltinVariable(Variable):
    pass


builtin_variables = {"print": BuiltinVariable("print", FunctionType([STRING], None))}


@dataclass(eq=False)
class GetVar(Expression):
    var: Variable
    lineno: Optional[int]

    def __init__(self, var: Variable, lineno: Optional[int] = None):
        super().__init__(var.type)
        self.var = var
        self.lineno = lineno


@dataclass(eq=False)
class StringConstant(Expression):
    value: str

    def __init__(self, value: str):
        super().__init__(STRING)
        self.value = value


@dataclass(eq=False)
class VoidCall(Statement):
    func: Expression
    args: List[Expression]


@dataclass(eq=False)
class ReturningCall(Expression, Statement):
    func: Expression
    args: List[Expression]

    def __init__(self, func: Expression, args: List[Expression]):
        assert isinstance(func.type, FunctionType)
        assert func.type.returntype is not None
        super().__init__(func.type.returntype)
        self.func = func
        self.args = args


@dataclass(eq=False)
class ToplevelDeclaration:
    pass


@dataclass(eq=False)
class FuncDef(ToplevelDeclaration):
    var: ExportVariable
    argvars: List[LocalVariable]
    body: List[Statement]
    refs: List[Tuple[str, Type]]


@dataclass(eq=False)
class Export:
    path: pathlib.Path
    name: str
    value: Union[ExportVariable, Type]  # Type includes UnionType
