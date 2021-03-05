from __future__ import annotations

import argparse
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


class CompilationUnit:
    c_path: pathlib.Path
    untyped_ast: List[uast.ToplevelDeclaration]

    def __init__(self, source_path: pathlib.Path):
        self.source_path = source_path

    def create_untyped_ast(self) -> None:
        with (project_root / "stdlib.oomph").open(encoding="utf-8") as file:
            stdlib_code = file.read()
        with self.source_path.open(encoding="utf-8") as file:
            source_code = file.read()

        self.untyped_ast = parser.parse_file(stdlib_code, None) + parser.parse_file(
            source_code, self.source_path
        )

    def create_c_code(
        self,
        used_c_paths: Set[pathlib.Path],
        compilation_dir: pathlib.Path,
        export_vars: List[tast.ExportVariable],
        export_var_names: Dict[tast.ExportVariable, str],
    ) -> None:
        self.c_path = compilation_dir / f"{self.source_path.stem}.c"
        counter = 0
        while self.c_path in used_c_paths:
            counter += 1
            self.c_path = compilation_dir / f"{self.source_path.stem}_{counter}.c"

        with self.c_path.open("w") as file:
            typed_ast = typer.convert_program(
                self.untyped_ast, self.source_path, export_vars
            )
            file.write(c_output.run(typed_ast, self.source_path, export_var_names))


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
    arg_parser.add_argument("--c-code", action="store_true")
    args = arg_parser.parse_args()

    assert not args.c_code  # TODO

    try:
        cache_dir = args.infile.parent / ".oomph-cache"
        cache_dir.mkdir(exist_ok=True)
    except OSError:
        cache_dir = pathlib.Path.cwd() / ".oomph-cache"
        cache_dir.mkdir(exist_ok=True)

    compilation_units: List[CompilationUnit] = []
    todo_list = [args.infile]
    while todo_list:
        source_path = todo_list.pop()
        if source_path in (unit.source_path for unit in compilation_units):
            raise RuntimeError("import cycle")

        unit = CompilationUnit(source_path)
        compilation_units.append(unit)
        unit.create_untyped_ast()

        for top_declaration in unit.untyped_ast:
            if isinstance(top_declaration, uast.Import):
                todo_list.append(top_declaration.path)

    # Compile dependencies first
    compilation_units.reverse()

    export_vars: List[tast.ExportVariable] = []
    export_var_names: Dict[tast.ExportVariable, str] = {}
    for index, unit in enumerate(compilation_units):
        already_compiled = compilation_units[:index]
        unit.create_c_code(
            {unit.c_path for unit in already_compiled},
            cache_dir,
            export_vars,
            export_var_names,
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
