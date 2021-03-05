from __future__ import annotations

import argparse
import os
import pathlib
import shlex
import signal
import subprocess
import sys
from typing import Dict, List, Set

from oomph import c_output, parser
from oomph import typed_ast as tast
from oomph import typer
from oomph import untyped_ast as uast

python_code_dir = pathlib.Path(__file__).absolute().parent
project_root = python_code_dir.parent


def _get_compiled_file_name(
    source_path: pathlib.Path, compilation_dir: pathlib.Path
) -> str:
    # TODO: avoid long file names
    return (
        source_path.stem
        + "_from_"
        + (
            os.path.relpath(source_path, compilation_dir.parent)
            .replace(".", "_dot_")
            .replace(os.sep, "_slash_")
        )
    )


class CompilationUnit:
    untyped_ast: List[uast.ToplevelDeclaration]

    def __init__(self, source_path: pathlib.Path, compilation_dir: pathlib.Path):
        name = _get_compiled_file_name(source_path, compilation_dir)
        self.source_path = source_path
        self.c_path = compilation_dir / (name + ".c")
        self.h_path = compilation_dir / (name + ".h")

    def create_untyped_ast(self) -> None:
        builtins_code = (project_root / "builtins.oomph").read_text(encoding="utf-8")
        source_code = self.source_path.read_text(encoding="utf-8")

        self.untyped_ast = parser.parse_file(
            builtins_code, None, None
        ) + parser.parse_file(source_code, self.source_path, project_root / "stdlib")

    def create_c_and_h_files(
        self,
        used_c_paths: Set[pathlib.Path],
        compilation_dir: pathlib.Path,
        exports: List[tast.Export],
        export_c_names: Dict[tast.Export, str],
        headers: List[str],
    ) -> None:
        typed_ast = typer.convert_program(
            self.untyped_ast, self.source_path, export_vars
        )
        c, h = c_output.run(typed_ast, self.source_path, exports, export_c_names)

        self.c_path.write_text(c, encoding="utf-8")
        self.h_path.write_text(h, encoding="utf-8")


def invoke_c_compiler(c_paths: List[pathlib.Path], exepath: pathlib.Path) -> int:
    compile_info = {}
    with (project_root / "obj" / "compile_info.txt").open() as file:
        for line in file:
            key, value = line.rstrip("\n").split("=", maxsplit=1)
            compile_info[key] = value

    return subprocess.run(
        [compile_info["cc"]]
        + shlex.split(compile_info["cflags"])
        + [str(path) for path in project_root.glob("obj/*.o")]
        + [str(path) for path in c_paths]
        + ["-o", str(exepath)]
        + shlex.split(compile_info["ldflags"])
        + ["-I", str(project_root)]
    ).returncode


def main() -> None:
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("infile", type=pathlib.Path)
    arg_parser.add_argument("--valgrind", action="store_true")
    args = arg_parser.parse_args()

    try:
        cache_dir = args.infile.parent / ".oomph-cache"
        cache_dir.mkdir(exist_ok=True)
    except OSError:
        cache_dir = pathlib.Path.cwd() / ".oomph-cache"
        cache_dir.mkdir(exist_ok=True)

    compilation_units: List[CompilationUnit] = []
    todo_list = [args.infile.absolute()]
    while todo_list:
        source_path = todo_list.pop()
        if source_path in (unit.source_path for unit in compilation_units):
            raise RuntimeError("import cycle")

        unit = CompilationUnit(source_path, cache_dir)
        compilation_units.append(unit)
        unit.create_untyped_ast()

        for top_declaration in unit.untyped_ast:
            if isinstance(top_declaration, uast.Import):
                todo_list.append(top_declaration.path)

    # Compile dependencies first
    compilation_units.reverse()

    exports: List[tast.Export] = []
    export_c_names: Dict[tast.Export, str] = {}
    for index, unit in enumerate(compilation_units):
        already_compiled = compilation_units[:index]
        unit.create_c_and_h_files(
            {unit.c_path for unit in already_compiled},
            cache_dir,
            exports,
            export_c_names,
            [unit.h_path.name for unit in already_compiled],
        )

    exe_path = cache_dir / args.infile.stem
    result = invoke_c_compiler([unit.c_path for unit in compilation_units], exe_path)
    if result != 0:
        sys.exit(result)

    if args.valgrind:
        command = [
            "valgrind",
            "-q",
            "--leak-check=full",
            "--show-leak-kinds=all",
            str(exe_path),
        ]
    else:
        command = [str(exe_path)]

    result = subprocess.run(command).returncode
    if result < 0:  # killed by signal
        message = f"Program killed by signal {abs(result)}"
        try:
            message += f" ({signal.Signals(abs(result)).name})"
        except ValueError:  # e.g. SIGRTMIN + 1
            pass
        print(message, file=sys.stderr)
    sys.exit(result)


main()
