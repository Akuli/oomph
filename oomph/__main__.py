from __future__ import annotations

import argparse
import pathlib
import shlex
import signal
import subprocess
import sys
from typing import IO, List

from oomph import c_output, parser
from oomph import typed_ast as tast
from oomph import typer

python_code_dir = pathlib.Path(__file__).absolute().parent
project_root = python_code_dir.parent


def invoke_c_compiler(exepath: pathlib.Path) -> subprocess.Popen[str]:
    compile_info = {}
    with open("obj/compile_info.txt") as file:
        for line in file:
            key, value = line.rstrip("\n").split("=", maxsplit=1)
            compile_info[key] = value

    return subprocess.Popen(
        [compile_info["cc"]]
        + shlex.split(compile_info["cflags"])
        + [str(path) for path in project_root.glob("obj/*.o")]
        + ["-x", "c", "-"]
        + ["-o", str(exepath)]
        + shlex.split(compile_info["ldflags"]),
        encoding="utf-8",
        stdin=subprocess.PIPE,
        cwd=project_root,
    )


def produce_c_code(source: IO[str], dest: IO[str]) -> None:
    with (project_root / "stdlib.oomph").open() as stdlib:
        code1 = stdlib.read()
    with source:
        code2 = source.read()
    dest.write(
        c_output.run(
            typer.convert_program(parser.parse_file(code1) + parser.parse_file(code2))
        )
    )


def main() -> None:
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("infile", type=argparse.FileType("r", encoding="utf-8"))
    arg_parser.add_argument("--valgrind", action="store_true")
    arg_parser.add_argument("--c-code", action="store_true")
    arg_parser.add_argument("--quiet", action="store_true")
    args = arg_parser.parse_args()

    input_path = pathlib.Path(args.infile.name).absolute()
    if args.c_code:
        produce_c_code(args.infile, sys.stdout)
        return

    try:
        exe_path = input_path.parent / ".oomph-cache" / input_path.stem
        exe_path.parent.mkdir(exist_ok=True)
    except OSError:
        exe_path = pathlib.Path.cwd() / ".oomph-cache" / input_path.stem
        exe_path.parent.mkdir(exist_ok=True)

    compile_deps = (
        [input_path, project_root / "stdlib.oomph"]
        + list(python_code_dir.rglob("*.py"))
        + list(project_root.glob("obj/*"))
    )
    try:
        exe_mtime = exe_path.stat().st_mtime
        skip_recompiling = all(exe_mtime > dep.stat().st_mtime for dep in compile_deps)
    except FileNotFoundError:
        skip_recompiling = False

    if not skip_recompiling:
        if not args.quiet:
            print("Must compile before running...", file=sys.stderr)

        with invoke_c_compiler(exe_path) as compiler_process:
            assert compiler_process.stdin is not None
            produce_c_code(args.infile, compiler_process.stdin)
            compiler_process.stdin.close()

            status = compiler_process.wait()
            if status != 0:
                sys.exit(status)

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
