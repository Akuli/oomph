from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


# Describes how exactly a type was created from a generic
@dataclass(eq=True)
class GenericSource:
    generic: Generic
    arg: Type


class Type:
    def __init__(
        self,
        name: str,
        refcounted: bool,
        definition_path: Optional[pathlib.Path] = None,
    ):
        self.name = name
        self.refcounted = refcounted
        self.definition_path = definition_path
        self.methods: Dict[str, FunctionType] = {}
        self.members: List[Tuple[Type, str]] = []
        self.constructor_argtypes: Optional[List[Type]] = None
        self.generic_origin: Optional[GenericSource] = None

    def __repr__(self) -> str:
        return f"<{type(self).__name__}: {self.name}>"

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, Type)
            and self.name == other.name
            and self.definition_path == other.definition_path
            and self.generic_origin == other.generic_origin
        )

    def __hash__(self) -> int:
        return hash(self.name)


class UnionType(Type):
    type_members: Optional[List[Type]]

    def __init__(self, name: str, definition_path: Optional[pathlib.Path] = None):
        super().__init__(name, True, definition_path)
        self.type_members = None  # to be set later
        self.methods["to_string"] = FunctionType([self], STRING)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {repr(self.name)}, type_members={self.type_members}>"

    def set_type_members(self, type_members: List[Type]) -> None:
        assert len(type_members) >= 2
        assert len(type_members) == len(set(type_members))  # no duplicates
        assert all(t.refcounted for t in type_members)  # TODO
        assert self.type_members is None
        self.type_members = type_members


# does NOT inherit from type, optional isn't a type even though optional[str] is
@dataclass(eq=False)
class Generic:
    name: str

    def get_type(self, generic_arg: Type) -> Type:
        if self is OPTIONAL:
            result = Type(f"{self.name}[{generic_arg.name}]", generic_arg.refcounted)
            result.generic_origin = GenericSource(self, generic_arg)
            result.constructor_argtypes = [generic_arg]
            result.methods["get"] = FunctionType([result], generic_arg)
            result.methods["equals"] = FunctionType([result, result], BOOL)
        elif self is LIST:
            result = Type(f"{self.name}[{generic_arg.name}]", True)
            result.generic_origin = GenericSource(self, generic_arg)
            result.constructor_argtypes = []
            result.methods["first"] = FunctionType([result], generic_arg)
            result.methods["get"] = FunctionType([result, INT], generic_arg)
            result.methods["last"] = FunctionType([result], generic_arg)
            result.methods["length"] = FunctionType([result], INT)
            result.methods["pop"] = FunctionType([result], generic_arg)
            result.methods["push"] = FunctionType([result, generic_arg], None)
            result.methods["push_all"] = FunctionType([result, result], None)
            result.methods["reversed"] = FunctionType([result], result)
            if generic_arg is STRING:
                result.methods["join"] = FunctionType([result, STRING], STRING)
        else:
            raise NotImplementedError

        result.methods["to_string"] = FunctionType([result], STRING)
        return result


LIST = Generic("List")
OPTIONAL = Generic("optional")


@dataclass(eq=False)
class FunctionType(Type):
    argtypes: List[Type]
    returntype: Optional[Type]

    def __init__(self, argtypes: List[Type], returntype: Optional[Type]):
        super().__init__("<function>", False)
        self.argtypes = argtypes
        self.returntype = returntype

    # Currently not used
    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, FunctionType)
            and self.argtypes == other.argtypes
            and self.returntype == other.returntype
        )

    def __hash__(self) -> int:
        return hash(tuple(self.argtypes)) ^ hash(self.returntype)


BOOL = Type("bool", False)
FLOAT = Type("float", False)
INT = Type("int", False)
STRING = Type("Str", True)

BOOL.methods["equals"] = FunctionType([BOOL, BOOL], BOOL)
BOOL.methods["to_string"] = FunctionType([BOOL], STRING)

FLOAT.methods["ceil"] = FunctionType([FLOAT], INT)
FLOAT.methods["equals"] = FunctionType([FLOAT, FLOAT], BOOL)
FLOAT.methods["floor"] = FunctionType([FLOAT], INT)
FLOAT.methods["round"] = FunctionType([FLOAT], INT)
FLOAT.methods["to_string"] = FunctionType([FLOAT], STRING)
FLOAT.methods["truncate"] = FunctionType([FLOAT], INT)

INT.methods["equals"] = FunctionType([INT, INT], BOOL)
INT.methods["to_string"] = FunctionType([INT], STRING)

STRING.methods["center_pad"] = FunctionType([STRING, INT, STRING], STRING)
STRING.methods["contains"] = FunctionType([STRING, STRING], BOOL)
STRING.methods["count"] = FunctionType([STRING, STRING], INT)
STRING.methods["ends_with"] = FunctionType([STRING, STRING], BOOL)
STRING.methods["equals"] = FunctionType([STRING, STRING], BOOL)
STRING.methods["find_first"] = FunctionType([STRING, STRING], OPTIONAL.get_type(INT))
STRING.methods["left_pad"] = FunctionType([STRING, INT, STRING], STRING)
STRING.methods["left_trim"] = FunctionType([STRING], STRING)
STRING.methods["length"] = FunctionType([STRING], INT)
STRING.methods["repeat"] = FunctionType([STRING, INT], STRING)
STRING.methods["replace"] = FunctionType([STRING, STRING, STRING], STRING)
STRING.methods["right_pad"] = FunctionType([STRING, INT, STRING], STRING)
STRING.methods["right_trim"] = FunctionType([STRING], STRING)
STRING.methods["slice"] = FunctionType([STRING, INT, INT], STRING)
STRING.methods["split"] = FunctionType([STRING, STRING], LIST.get_type(STRING))
STRING.methods["starts_with"] = FunctionType([STRING, STRING], BOOL)
STRING.methods["to_float"] = FunctionType([STRING], FLOAT)
STRING.methods["to_int"] = FunctionType([STRING], INT)
STRING.methods["to_string"] = FunctionType([STRING], STRING)  # does nothing
STRING.methods["trim"] = FunctionType([STRING], STRING)
STRING.methods["unicode_length"] = FunctionType([STRING], INT)

builtin_types = {typ.name: typ for typ in [INT, FLOAT, BOOL, STRING]}
builtin_generic_types = {gen.name: gen for gen in [OPTIONAL, LIST]}
