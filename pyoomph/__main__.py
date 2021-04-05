from __future__ import annotations

import argparse
import atexit
import itertools
import shlex
import shutil
import signal
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pyoomph import ast, ast2ir, ast_transformer, c_output, ir, parser

python_code_dir = Path(__file__).absolute().parent
project_root = python_code_dir.parent


class CompilationUnit:
    ast: List[ast.ToplevelDeclaration]

    def __init__(self, source_path: Path, session: c_output.Session):
        self.source_path = source_path
        self.session = session

    def _handle_error(self) -> None:
        traceback.print_exc()
        print(f"\nThis happened while compiling {self.source_path}", file=sys.stderr)
        sys.exit(1)

    def create_untyped_ast(self) -> None:
        try:
            source_code = self.source_path.read_text(encoding="utf-8")
            self.ast = ast_transformer.transform_file(
                parser.parse_file(
                    source_code, self.source_path, project_root / "stdlib"
                )
            )
        except Exception:
            self._handle_error()

    def create_c_code(self, exports: List[ir.Symbol]) -> None:
        try:
            the_ir = ast2ir.convert_program(self.ast, self.source_path, exports)
            self.session.create_c_code(the_ir, self.source_path)
        except Exception:
            self._handle_error()


def get_c_compiler_command(c_paths: List[Path], exepath: Path) -> Tuple[List[str], str]:
    compile_info = {}
    with (project_root / "obj" / "compile_info.txt").open() as file:
        for line in file:
            key, value = line.rstrip("\n").split("=", maxsplit=1)
            compile_info[key] = value

    before_files = (
        [compile_info["cc"]]
        + shlex.split(compile_info["cflags"])
        + [str(path) for path in project_root.glob("obj/*.o")]
    )
    after_files = (
        ["-o", str(exepath)]
        + shlex.split(compile_info["ldflags"])
        + ["-I", str(project_root)]
    )
    return (
        before_files + [str(path) for path in c_paths] + after_files,
        " ".join(
            [shlex.quote(arg) for arg in before_files]
            + [f"<{len(c_paths)} files>"]
            + [shlex.quote(arg) for arg in after_files]
        ),
    )


def run(command: List[str], verbose: bool, human_readable: Optional[str] = None) -> int:
    if verbose:
        if human_readable is None:
            human_readable = " ".join(map(shlex.quote, command))
        print("Running:", human_readable, file=sys.stderr)
    return subprocess.run(command).returncode


def get_compilation_dir(parent_dir: Path, name_hint: str) -> Path:
    for i in itertools.count():
        path = parent_dir / (name_hint + str(i))
        path.mkdir(parents=True, exist_ok=True)
        try:
            (path / "compiling").touch(exist_ok=False)
        except FileExistsError:
            # Another instance of oomph compiler running in parallel
            continue
        else:
            atexit.register((path / "compiling").unlink)
            return path
    assert False  # make mypy feel good


def compute_dependency_graph(
    session: c_output.Session,
    infile: Path,
    verbose: bool,
) -> Dict[CompilationUnit, List[Path]]:
    dependency_graph: Dict[CompilationUnit, List[Path]] = {}
    queue = [infile]
    while queue:
        # Pop the next source file to parse
        source_path = queue.pop()
        if source_path in (unit.source_path for unit in dependency_graph.keys()):
            continue
        if verbose:
            print("Parsing", source_path)

        # Create a compilation unit out of it and parse it into an untyped ast
        candidate_unit = CompilationUnit(source_path, session)
        candidate_unit.create_untyped_ast()

        # Calculate its dependencies and add them to the dependencies dictionary,
        # including builtins if necessary, and add those dependencies to the queue
        current_dependencies = [
            top_declaration.path
            for top_declaration in candidate_unit.ast
            if isinstance(top_declaration, ast.Import)
        ]
        if source_path != project_root / "builtins.oomph":
            current_dependencies.append(project_root / "builtins.oomph")
        dependency_graph[candidate_unit] = current_dependencies
        queue.extend(current_dependencies)
    return dependency_graph


def compute_compilation_order(
    verbose: bool,
    dependency_graph: Dict[CompilationUnit, List[Path]],
) -> List[CompilationUnit]:
    compilation_order: List[CompilationUnit] = []
    while len(compilation_order) < len(dependency_graph):
        candidate_unit = next(
            u for u in dependency_graph.keys() if u not in compilation_order
        )
        breadcrumbs = [candidate_unit]
        while True:
            uncompiled_dependencies = [
                u
                for u in dependency_graph.keys()
                if u not in compilation_order
                and u.source_path in dependency_graph[candidate_unit]
            ]
            if not uncompiled_dependencies:
                break
            if verbose:
                print(
                    f"Noticed dependency: {candidate_unit.source_path} --> {uncompiled_dependencies[0].source_path}"
                )
            candidate_unit = uncompiled_dependencies[0]
            if candidate_unit in breadcrumbs:
                message = (
                    " --> ".join(d.source_path.name for d in breadcrumbs)
                    + " --> "
                    + candidate_unit.source_path.name
                )
                raise RuntimeError("cyclic imports: " + message)
            breadcrumbs.append(candidate_unit)
        compilation_order.append(candidate_unit)
    return compilation_order


def main() -> None:
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("infile", type=Path)
    arg_parser.add_argument("-o", "--outfile", type=Path)
    arg_parser.add_argument("--valgrind", default="")
    arg_parser.add_argument("-v", "--verbose", action="store_true")
    compiler_args, program_args = arg_parser.parse_known_args()

    try:
        cache_dir = compiler_args.infile.parent / ".oomph-cache"
        cache_dir.mkdir(exist_ok=True)
    except OSError:
        cache_dir = Path.cwd() / ".oomph-cache"
        cache_dir.mkdir(exist_ok=True)

    # Create a compiler session
    session = c_output.Session(
        get_compilation_dir(cache_dir, compiler_args.infile.stem + "_compilation")
    )

    # Calculate the dependency graph
    dependency_graph = compute_dependency_graph(
        session, compiler_args.infile.absolute(), compiler_args.verbose
    )

    # Calculate in which order we need to compile our units
    compilation_order = compute_compilation_order(
        compiler_args.verbose, dependency_graph
    )

    # Compile in the calculated order
    for unit in compilation_order:
        if compiler_args.verbose:
            print("Creating C code:", unit.source_path)
        unit.create_c_code(session.symbols)

    # Write out everything and compile it
    c_paths = session.write_everything(project_root / "builtins.oomph")
    exe_path = session.compilation_dir / compiler_args.infile.stem
    command, human_readable_command = get_c_compiler_command(c_paths, exe_path)
    result = run(command, compiler_args.verbose, human_readable_command)
    if result != 0:
        sys.exit(result)

    # If we have an outfile path, move the resulting executable to it and bail
    if compiler_args.outfile is not None:
        assert not compiler_args.outfile.is_dir()  # shutil.move is weird for dirs
        shutil.move(str(exe_path), str(compiler_args.outfile))
        if compiler_args.verbose:
            print("Moved executable to", compiler_args.outfile)
        return

    # Otherwise, run it directly
    command = shlex.split(compiler_args.valgrind) + [str(exe_path)] + program_args
    result = run(command, compiler_args.verbose)
    if result < 0:  # killed by signal
        message = f"Program killed by signal {abs(result)}"
        try:
            message += f" ({signal.Signals(abs(result)).name})"
        except ValueError:  # e.g. SIGRTMIN + 1
            pass
        print(message, file=sys.stderr)
    elif result > 0:
        print(f"Program exited with status {result}", file=sys.stderr)
    sys.exit(result)


main()
