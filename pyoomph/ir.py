from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import List, Optional, Union

from pyoomph.types import (
    BOOL,
    FLOAT,
    INT,
    LIST,
    NULL_TYPE,
    STRING,
    FunctionType,
    Type,
    UnionType,
)


# There can be different local variables with same name, even in the same
# function. They are represented as different instances of this class.
#
# A local variable holds a reference. They are decreffed automatically when the
# function exits.
@dataclass(eq=False)
class LocalVariable:
    type: Type

    # Default dataclass repr does not distinguish different instances
    def __repr__(self) -> str:
        return "<LocalVariable %s: %s>" % (hex(id(self))[-4:], self.type.name)


@dataclass(eq=False)
class FileVariable:
    name: str
    type: Type
    source_path: pathlib.Path


@dataclass(eq=False)
class BuiltinVariable:
    name: str
    type: Type


Variable = Union[LocalVariable, FileVariable, BuiltinVariable]


visible_builtins = {
    var.name: var
    for var in [
        BuiltinVariable("__argv_count", FunctionType([], INT)),
        BuiltinVariable("__argv_get", FunctionType([INT], STRING)),
        BuiltinVariable("__get_first_char", FunctionType([STRING], STRING)),
        BuiltinVariable("__get_utf8_byte", FunctionType([STRING, INT], INT)),
        BuiltinVariable("__hash", FunctionType([STRING, STRING], STRING)),
        BuiltinVariable("__io_mkdir", FunctionType([STRING], None)),
        BuiltinVariable("__io_read_file", FunctionType([STRING], STRING)),
        BuiltinVariable("__io_write_file", FunctionType([STRING, STRING], None)),
        BuiltinVariable("__remove_prefix", FunctionType([STRING, STRING], STRING)),
        BuiltinVariable("__remove_suffix", FunctionType([STRING, STRING], STRING)),
        BuiltinVariable("__run_subprocess", FunctionType([LIST.get_type(STRING)], INT)),
        BuiltinVariable(
            "__slice_until_substring", FunctionType([STRING, STRING], STRING)
        ),
        BuiltinVariable("assert", FunctionType([BOOL, STRING, INT], None)),
        BuiltinVariable("false", BOOL),
        BuiltinVariable("null", NULL_TYPE),
        BuiltinVariable("print", FunctionType([STRING], None)),
        BuiltinVariable("true", BOOL),
    ]
}

# Not exposed into oomph programs
hidden_builtins = {
    var.name: var
    for var in [
        BuiltinVariable("bool_eq", FunctionType([BOOL, BOOL], BOOL)),
        BuiltinVariable("bool_not", FunctionType([BOOL], BOOL)),
        BuiltinVariable("float_add", FunctionType([FLOAT, FLOAT], FLOAT)),
        BuiltinVariable("float_div", FunctionType([FLOAT, FLOAT], FLOAT)),
        BuiltinVariable("float_eq", FunctionType([FLOAT, FLOAT], BOOL)),
        BuiltinVariable("float_gt", FunctionType([FLOAT, FLOAT], BOOL)),
        BuiltinVariable("float_mod", FunctionType([FLOAT, FLOAT], FLOAT)),
        BuiltinVariable("float_mul", FunctionType([FLOAT, FLOAT], FLOAT)),
        BuiltinVariable("float_neg", FunctionType([FLOAT], FLOAT)),
        BuiltinVariable("float_sub", FunctionType([FLOAT, FLOAT], FLOAT)),
        BuiltinVariable("int2float", FunctionType([INT], FLOAT)),
        BuiltinVariable("int_add", FunctionType([INT, INT], INT)),
        BuiltinVariable("int_eq", FunctionType([INT, INT], BOOL)),
        BuiltinVariable("int_gt", FunctionType([INT, INT], BOOL)),
        BuiltinVariable("int_mod", FunctionType([INT, INT], INT)),
        BuiltinVariable("int_mul", FunctionType([INT, INT], INT)),
        BuiltinVariable("int_neg", FunctionType([INT], INT)),
        BuiltinVariable("int_sub", FunctionType([INT, INT], INT)),
        BuiltinVariable("string_concat", FunctionType([STRING, STRING], STRING)),
        BuiltinVariable("string_eq", FunctionType([STRING, STRING], BOOL)),
    ]
}


@dataclass(eq=False)
class Instruction:
    pass


@dataclass(eq=False)
class VarCpy(Instruction):
    # Arguments are same order as memcpy
    dest: LocalVariable
    source: Variable


@dataclass(eq=False)
class GetAttribute(Instruction):
    obj: LocalVariable
    result: LocalVariable
    attribute: str


@dataclass(eq=False)
class SetAttribute(Instruction):
    obj: LocalVariable
    attribute: str
    value: LocalVariable

    def __post_init__(self) -> None:
        assert (self.value.type, self.attribute) in self.obj.type.members


# Currently you can't use a function, method or ctor without immediately calling it
@dataclass(eq=False)
class CallMethod(Instruction):
    obj: LocalVariable
    method_name: str
    args: List[LocalVariable]
    result: Optional[LocalVariable]


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
    var: LocalVariable
    value: str


@dataclass(eq=False)
class IntConstant(Instruction):
    var: LocalVariable
    value: int


@dataclass(eq=False)
class FloatConstant(Instruction):
    var: LocalVariable
    value: str


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
        assert (
            self.value.type in self.result.type.type_members
        ), f"wrong types in union instantiation: {self.value}"


# IncRef and DecRef don't do anything if variable is set to null
@dataclass(eq=False)
class IncRef(Instruction):
    var: LocalVariable


@dataclass(eq=False)
class DecRef(Instruction):
    var: LocalVariable


@dataclass(eq=False)
class UnSet(Instruction):
    var: LocalVariable


# TODO: replace Return with gotos?
@dataclass(eq=False)
class Return(Instruction):
    value: Optional[LocalVariable]


@dataclass(eq=False, repr=False)
class GotoLabel(Instruction):
    pass


@dataclass(eq=False)
class Goto(Instruction):
    label: GotoLabel
    cond: Union[BuiltinVariable, LocalVariable]  # can be set to builtin true

    def __post_init__(self) -> None:
        assert self.cond.type == BOOL


# Runtime error if trying to get wrong union member
# think of it as VarCpy for unions
@dataclass(eq=False)
class GetFromUnion(Instruction):
    result: LocalVariable
    union: LocalVariable


# Check is it possible to call GetFromUnion with result var of given member type
@dataclass(eq=False)
class UnionMemberCheck(Instruction):
    result: LocalVariable
    union: LocalVariable
    member_type: Type


@dataclass(eq=False)
class ToplevelDeclaration:
    pass


@dataclass(eq=False)
class FuncDef(ToplevelDeclaration):
    var: FileVariable
    argvars: List[LocalVariable]
    body: List[Instruction]


@dataclass(eq=False)
class MethodDef(ToplevelDeclaration):
    name: str
    type: FunctionType
    argvars: List[LocalVariable]
    body: List[Instruction]


# Anything that might need to be shared between different .c files
@dataclass(eq=False)
class Symbol:
    path: pathlib.Path
    name: str
    value: Union[FileVariable, Type]  # Type includes UnionType
