from __future__ import annotations

import argparse
import pathlib
import shlex
import subprocess
from typing import List

from oomphmini import c_output, parser, typer

project_root = pathlib.Path(__file__).absolute().parent.parent


def get_c_compiler_command(c_path: pathlib.Path, exepath: pathlib.Path) -> List[str]:
    compile_info = {}
    with (project_root / "obj" / "compile_info.txt").open() as file:
        for line in file:
            key, value = line.rstrip("\n").split("=", maxsplit=1)
            compile_info[key] = value

    return (
        [compile_info["cc"]]
        + shlex.split(compile_info["cflags"])
        + [str(path) for path in project_root.glob("obj/*.o")]
        + [str(c_path)]
        + ["-o", str(exepath)]
        + shlex.split(compile_info["ldflags"])
        + ["-I", str(project_root)]
    )


def main() -> None:
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("infile", type=pathlib.Path)
    args = arg_parser.parse_args()

    cache_dir = args.infile.parent / ".oomph-cache"
    cache_dir.mkdir(exist_ok=True)

    source_path = args.infile.absolute()
    c_path = cache_dir / "out.c"
    h_path = cache_dir / "out.h"
    source_code = source_path.read_text(encoding="utf-8")
    untyped_ast = parser.parse_file(source_code, source_path, None)

    session = c_output.Session()
    typed_ast = typer.convert_program(untyped_ast, source_path, session.exports)
    c, h = session.create_c_code(typed_ast)

    c_path.write_text(c, encoding="utf-8")
    h_path.write_text(h, encoding="utf-8")

    exe_path = cache_dir / args.infile.stem
    command = get_c_compiler_command(c_path, exe_path)

    result = subprocess.run(command).returncode
    assert result == 0
    result = subprocess.run([str(exe_path)]).returncode
    assert result == 0


main()
