from __future__ import annotations

import argparse
import os
import pathlib
import shlex
import subprocess
import sys
from typing import IO, Any

from compiler import c_output, parser, tokenizer, typer

project_root = pathlib.Path(__file__).absolute().parent.parent


def invoke_c_compiler(exepath: pathlib.Path) -> subprocess.Popen[str]:
    compile_info = {}
    with open("obj/compile_info.txt") as file:
        for line in file:
            key, value = line.rstrip("\n").split("=", maxsplit=1)
            compile_info[key] = value

    return subprocess.Popen(
        [compile_info["cc"]]
        + shlex.split(compile_info["cflags"])
        + shlex.split(os.environ.get("CFLAGS", ""))
        + [str(path) for path in project_root.glob("obj/*") if path.suffix != ".txt"]
        + ["-x", "c", "-"]
        + ["-o", str(exepath)]
        + shlex.split(compile_info["ldflags"])
        + shlex.split(os.environ.get("LDFLAGS", "")),
        encoding="utf-8",
        stdin=subprocess.PIPE,
        cwd=project_root,
    )


def produce_c_code(args: Any, dest: IO[str]) -> None:
    with args.infile:
        code = args.infile.read()

    dest.write('#include "lib/lib.h"\n')
    for toplevel_statement in typer.convert_program(
        parser.parse_file(tokenizer.tokenize(code))
    ):
        c_output.emit_toplevel_statement(dest, toplevel_statement)


def main() -> None:
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("infile", type=argparse.FileType("r", encoding="utf-8"))
    arg_parser.add_argument("--valgrind", action="store_true")
    arg_parser.add_argument("--c-code", action="store_true")
    args = arg_parser.parse_args()

    input_path = pathlib.Path(args.infile.name).absolute()
    if args.c_code:
        produce_c_code(args, sys.stdout)
        return

    exe_path = input_path.parent / ".compiler-cache" / input_path.stem
    exe_path.parent.mkdir(exist_ok=True)

    compile_deps = [input_path] + list(project_root.glob("obj/*"))
    try:
        exe_mtime = exe_path.stat().st_mtime
        skip_recompiling = all(exe_mtime > dep.stat().st_mtime for dep in compile_deps)
    except FileNotFoundError:
        skip_recompiling = False

    if not skip_recompiling:
        print("Compiling...", file=sys.stderr)
        with invoke_c_compiler(exe_path) as compiler_process:
            assert compiler_process.stdin is not None
            produce_c_code(args, compiler_process.stdin)
            compiler_process.stdin.close()

            status = compiler_process.wait()
            if status != 0:
                sys.exit(status)

    if args.valgrind:
        command = ["valgrind", "-q", "--leak-check=full", "--show-leak-kinds=all", str(exe_path)]
    else:
        command = [str(exe_path)]
    sys.exit(subprocess.run(command).returncode)


main()
