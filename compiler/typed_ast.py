import copy
from dataclasses import dataclass
from typing import List, Optional, Tuple

from compiler.types import BOOL, FLOAT, INT, ClassType, FunctionType, Type


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

    def __init__(self, obj: Expression, attribute: str):
        assert isinstance(obj.type, ClassType)
        the_type = {name: the_type for the_type, name in obj.type.members}[attribute]
        super().__init__(the_type)
        self.obj = obj
        self.attribute = attribute


@dataclass
class GetMethod(Expression):
    obj: Expression
    name: str

    def __init__(self, obj: Expression, name: str):
        assert isinstance(obj.type, ClassType)
        the_type = copy.copy(obj.type.methods[name])  # shallow copy
        self_type = the_type.argtypes[0]
        assert self_type is obj.type
        the_type.argtypes = the_type.argtypes[1:]  # don't modify in-place

        super().__init__(the_type)
        self.obj = obj
        self.name = name


@dataclass
class IntConstant(Expression):
    value: int

    def __init__(self, value: int):
        super().__init__(INT)
        self.value = value


@dataclass
class BoolConstant(Expression):
    value: bool

    def __init__(self, value: bool):
        super().__init__(BOOL)
        self.value = value


@dataclass
class FloatConstant(Expression):
    value: str

    def __init__(self, value: str):
        super().__init__(FLOAT)
        self.value = value


@dataclass
class IntToFloat(Expression):
    value: Expression

    def __init__(self, value: Expression):
        super().__init__(FLOAT)
        self.value = value


@dataclass
class NumberAdd(Expression):
    lhs: Expression
    rhs: Expression


@dataclass
class NumberNegation(Expression):
    obj: Expression


@dataclass
class NumberSub(Expression):
    lhs: Expression
    rhs: Expression


@dataclass
class NumberMul(Expression):
    lhs: Expression
    rhs: Expression


@dataclass
class FloatDiv(Expression):
    lhs: Expression
    rhs: Expression

    def __init__(self, lhs: Expression, rhs: Expression):
        assert lhs.type is FLOAT
        assert rhs.type is FLOAT
        super().__init__(FLOAT)
        self.lhs = lhs
        self.rhs = rhs


@dataclass
class BoolAnd(Expression):
    lhs: Expression
    rhs: Expression

    def __init__(self, lhs: Expression, rhs: Expression):
        super().__init__(BOOL)
        self.lhs = lhs
        self.rhs = rhs


@dataclass
class BoolNot(Expression):
    obj: Expression

    def __init__(self, obj: Expression):
        super().__init__(BOOL)
        self.obj = obj


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
    value: Optional[Expression]


@dataclass
class ToplevelStatement:
    pass


@dataclass
class FuncDef(ToplevelStatement):
    name: str
    type: FunctionType
    argnames: List[str]
    body: List[Statement]
    refs: List[Tuple[str, Type]]


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
