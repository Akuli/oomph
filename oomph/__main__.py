from __future__ import annotations

import argparse
import pathlib
import shlex
import signal
import subprocess
import sys
from typing import Dict, List

from oomph import c_output, parser
from oomph import typed_ast as tast
from oomph import typer
from oomph import untyped_ast as uast

python_code_dir = pathlib.Path(__file__).absolute().parent
project_root = python_code_dir.parent


def create_untyped_ast(source_path: pathlib.Path) -> List[uast.ToplevelDeclaration]:
    with (project_root / "stdlib.oomph").open(encoding="utf-8") as file:
        stdlib_code = file.read()
    with source_path.open(encoding="utf-8") as file:
        source_code = file.read()

    return parser.parse_file(stdlib_code, None) + parser.parse_file(
        source_code, source_path
    )


def create_c_code(
    untyped_ast: List[uast.ToplevelDeclaration],
    source_path: pathlib.Path,
    export_vars: List[tast.ExportVariable],
    export_var_names: Dict[tast.ExportVariable, str],
) -> str:
    typed_ast = typer.convert_program(untyped_ast, source_path, export_vars)
    return c_output.run(typed_ast, source_path, export_var_names)


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

    c_paths: Dict[pathlib.Path, pathlib.Path] = {}
    untyped_asts: Dict[pathlib.Path, List[uast.ToplevelDeclaration]] = {}
    todo_list = [args.infile]
    compilation_order: List[pathlib.Path] = []

    while todo_list:
        source_path = todo_list.pop()
        if source_path in c_paths:
            raise RuntimeError("import cycle")

        c_path = cache_dir / f"{source_path.stem}.c"
        counter = 0
        while c_path in c_paths:
            counter += 1
            cache_dir / f"{source_path.stem}_{counter}.c"
        c_paths[source_path] = c_path
        compilation_order.append(source_path)

        untyped_asts[source_path] = create_untyped_ast(source_path)
        for top_declaration in untyped_asts[source_path]:
            if isinstance(top_declaration, uast.Import):
                todo_list.append(top_declaration.path)

    compilation_order.reverse()

    export_vars: List[tast.ExportVariable] = []
    export_var_names: Dict[tast.ExportVariable, str] = {}
    for source_path in compilation_order:
        with c_paths[source_path].open("w") as file:
            file.write(
                create_c_code(
                    untyped_asts[source_path],
                    source_path,
                    export_vars,
                    export_var_names,
                )
            )

    exe_path = cache_dir / args.infile.stem
    result = invoke_c_compiler([c_paths[s] for s in compilation_order], exe_path)
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
