# TODO: rename this, it's no longer ast
from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Union

from pyoomph.types import BOOL, FLOAT, INT, LIST, STRING, FunctionType, Type, UnionType


@dataclass(eq=False)
class Instruction:
    pass


# There can be different local variables with same name, even in the same
# function. They are represented as different instances of this class.
# TODO: make name optional
#
# A local variable holds a reference. They are decreffed automatically when the
# function exits.
@dataclass(eq=False)
class LocalVariable:
    type: Type


# Currently these are always functions. These would be called "global
# variables" in Python, but that's confusing, because they are less global
# than ExportVariables.
@dataclass(eq=False)
class ThisFileVariable:
    name: str
    type: Type


@dataclass(eq=False)
class ExportVariable:
    name: str
    type: Type


@dataclass(eq=False)
class BuiltinVariable:
    name: str
    type: Type


@dataclass(eq=False)
class SpecialVariable:
    name: str
    type: Type


Variable = Union[
    LocalVariable, ThisFileVariable, ExportVariable, BuiltinVariable, SpecialVariable
]


builtin_variables = {
    var.name: var
    for var in [
        BuiltinVariable("__io_mkdir", FunctionType([STRING], None)),
        BuiltinVariable("__io_read_file", FunctionType([STRING], STRING)),
        BuiltinVariable("__io_write_file", FunctionType([STRING, STRING], None)),
        BuiltinVariable("__subprocess_run", FunctionType([LIST.get_type(STRING)], INT)),
        BuiltinVariable("assert", FunctionType([BOOL, INT], None)),
        BuiltinVariable("false", BOOL),
        BuiltinVariable("print", FunctionType([STRING], None)),
        BuiltinVariable("true", BOOL),
    ]
}

special_variables = {
    var.name: var
    for var in [
        SpecialVariable("bool_eq", FunctionType([BOOL, BOOL], BOOL)),
        SpecialVariable("bool_not", FunctionType([BOOL], BOOL)),
        SpecialVariable("float_add", FunctionType([FLOAT, FLOAT], FLOAT)),
        SpecialVariable("float_div", FunctionType([FLOAT, FLOAT], FLOAT)),
        SpecialVariable("float_eq", FunctionType([FLOAT, FLOAT], BOOL)),
        SpecialVariable("float_gt", FunctionType([FLOAT, FLOAT], BOOL)),
        SpecialVariable("float_mod", FunctionType([FLOAT, FLOAT], FLOAT)),
        SpecialVariable("float_mul", FunctionType([FLOAT, FLOAT], FLOAT)),
        SpecialVariable("float_neg", FunctionType([FLOAT], FLOAT)),
        SpecialVariable("float_sub", FunctionType([FLOAT, FLOAT], FLOAT)),
        SpecialVariable("int2float", FunctionType([INT], FLOAT)),
        SpecialVariable("int_add", FunctionType([INT, INT], INT)),
        SpecialVariable("int_eq", FunctionType([INT, INT], BOOL)),
        SpecialVariable("int_gt", FunctionType([INT, INT], BOOL)),
        SpecialVariable("int_mod", FunctionType([INT, INT], INT)),
        SpecialVariable("int_mul", FunctionType([INT, INT], INT)),
        SpecialVariable("int_neg", FunctionType([INT], INT)),
        SpecialVariable("int_sub", FunctionType([INT, INT], INT)),
        SpecialVariable("string_concat", FunctionType([STRING, STRING], STRING)),
        SpecialVariable("string_eq", FunctionType([STRING, STRING], BOOL)),
    ]
}


@dataclass(eq=False)
class VarCpy(Instruction):
    # Arguments are same order as memcpy
    dest: LocalVariable
    source: Variable

    def __post_init__(self) -> None:
        assert self.dest.type == self.source.type


@dataclass(eq=False)
class GetAttribute(Instruction):
    obj: LocalVariable
    result: LocalVariable
    attribute: str

    def __post_init__(self) -> None:
        assert (self.result.type, self.attribute) in self.obj.type.members


# Currently you can't use a function, method or ctor without immediately calling it
@dataclass(eq=False)
class CallMethod(Instruction):
    obj: LocalVariable
    method_name: str
    args: List[LocalVariable]
    result: Optional[LocalVariable]

    def __post_init__(self) -> None:
        functype = self.obj.type.methods[self.method_name]
        if functype.returntype is None:
            assert self.result is None
        else:
            assert self.result is not None
            assert self.result.type == functype.returntype
        assert [self.obj.type] + [
            arg.type for arg in self.args
        ] == functype.argtypes, self.method_name


@dataclass(eq=False)
class CallFunction(Instruction):
    func: Variable
    args: List[LocalVariable]
    result: Optional[LocalVariable]

    def __post_init__(self) -> None:
        assert not isinstance(self.func, LocalVariable)
        assert isinstance(self.func.type, FunctionType)
        if self.func.type.returntype is None:
            assert self.result is None
        else:
            assert self.result is not None
            assert self.result.type == self.func.type.returntype
        assert [arg.type for arg in self.args] == self.func.type.argtypes, (
            self.func,
            self.args,
        )


@dataclass(eq=False)
class CallConstructor(Instruction):
    result: LocalVariable
    args: List[LocalVariable]

    def __post_init__(self) -> None:
        assert self.result.type.constructor_argtypes is not None
        assert [arg.type for arg in self.args] == self.result.type.constructor_argtypes


@dataclass(eq=False)
class StringConstant(Instruction):
    result: LocalVariable
    value: str


@dataclass(eq=False)
class IntConstant(Instruction):
    result: LocalVariable
    value: int


@dataclass(eq=False)
class FloatConstant(Instruction):
    result: LocalVariable
    value: str


@dataclass(eq=False)
class Null(Instruction):
    result: LocalVariable


# Can't be a function call because arguments can be many different types
@dataclass(eq=False)
class PointersEqual(Instruction):
    lhs: LocalVariable
    rhs: LocalVariable
    result: LocalVariable

    def __post_init__(self) -> None:
        assert self.lhs.type.refcounted
        assert self.rhs.type.refcounted
        assert self.result.type == BOOL


@dataclass(eq=False)
class InstantiateUnion(Instruction):
    result: LocalVariable
    value: LocalVariable

    def __post_init__(self) -> None:
        assert isinstance(self.result.type, UnionType)
        assert self.result.type.type_members is not None
        assert self.value.type in self.result.type.type_members


# IncRef and DecRef don't do anything if variable is unset
@dataclass(eq=False)
class IncRef(Instruction):
    var: LocalVariable


@dataclass(eq=False)
class DecRef(Instruction):
    var: LocalVariable


@dataclass(eq=False)
class Continue(Instruction):
    loop_id: str


@dataclass(eq=False)
class Break(Instruction):
    loop_id: str


@dataclass(eq=False)
class Return(Instruction):
    value: Optional[LocalVariable]


@dataclass(eq=False)
class If(Instruction):
    condition: LocalVariable
    then: List[Instruction]
    otherwise: List[Instruction]

    def __post_init__(self) -> None:
        assert self.condition.type == BOOL


@dataclass(eq=False)
class Loop(Instruction):
    loop_id: str
    cond_code: List[Instruction]
    cond: LocalVariable
    incr: List[Instruction]
    body: List[Instruction]

    def __post_init__(self) -> None:
        assert self.cond.type == BOOL


# errors if trying to get wrong type
# think of it as VarCpy for unions
@dataclass(eq=False)
class GetFromUnion(Instruction):
    result: LocalVariable
    union: LocalVariable


# TODO: replace with nested Ifs or something like that?
@dataclass(eq=False)
class Switch(Instruction):
    union: LocalVariable
    cases: Dict[Type, List[Instruction]]


@dataclass(eq=False)
class Constructor(Instruction):
    result: LocalVariable


@dataclass(eq=False)
class ToplevelDeclaration:
    pass


@dataclass(eq=False)
class FuncDef(ToplevelDeclaration):
    var: Union[ThisFileVariable, ExportVariable]
    argvars: List[LocalVariable]
    body: List[Instruction]


@dataclass(eq=False)
class MethodDef:
    name: str
    type: FunctionType
    argvars: List[LocalVariable]
    body: List[Instruction]


@dataclass(eq=False)
class ClassDef(ToplevelDeclaration):
    type: Type
    body: List[MethodDef]
    export: bool


@dataclass(eq=False)
class UnionDef(ToplevelDeclaration):
    type: UnionType


@dataclass(eq=False)
class Export:
    path: pathlib.Path
    name: str
    value: Union[ExportVariable, Type]  # Type includes UnionType
