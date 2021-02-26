import argparse
import io
import os
import pathlib
import shlex
import subprocess
import sys

from compiler import c_output, parser, tokenizer, typer


project_root = pathlib.Path(__file__).absolute().parent.parent


def invoke_c_compiler(code: str, outpath: pathlib.Path) -> subprocess.Popen:
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
        + ["-o", str(outpath)]
        + shlex.split(compile_info["ldflags"])
        + shlex.split(os.environ.get("LDFLAGS", "")),
        stdin=subprocess.PIPE,
        cwd=project_root,
    )


def main() -> None:
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("infile", type=argparse.FileType("r", encoding="utf-8"))
    args = arg_parser.parse_args()

    input_path = pathlib.Path(args.infile.name).absolute()
    exe_path = input_path.parent / ".compiler-cache" / input_path.name
    exe_path.parent.mkdir(exist_ok=True)

    compile_deps = [input_path] + list(project_root.glob("obj/*"))

    try:
        exe_mtime = exe_path.stat().st_mtime
        skip_recompiling = all(exe_mtime > dep.stat().st_mtime for dep in compile_deps)
    except FileNotFoundError:
        skip_recompiling = False

    if not skip_recompiling:
        print("Compiling", file=sys.stderr)
        with args.infile:
            code = args.infile.read()

        compiler_process = invoke_c_compiler()
        stdin = io.TextIOWrapper(compiler_process.stdin)
        stdin.write('#include "lib/lib.h"\n')
        for toplevel_statement in typer.convert_program(
            parser.parse_file(tokenizer.tokenize(code))
        ):
            c_output.emit_toplevel_statement(stdin, toplevel_statement)

        stdin.close()
        status = compiler_process.wait()
        if status != 0:
            sys.exit(status)

    sys.exit(subprocess.run([exe_path]).returncode)


main()
