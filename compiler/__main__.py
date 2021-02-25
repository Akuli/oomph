import argparse
import os

from compiler import c_output, parser, tokenizer, typer


def main() -> None:
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('inpath', type=os.path.abspath)   # type: ignore
    arg_parser.add_argument('outpath', type=os.path.abspath)  # type: ignore
    args = arg_parser.parse_args()

    with open(args.inpath, 'r', encoding='utf-8') as file:
        code = file.read()

    parsed = typer.convert_program(parser.parse_file(tokenizer.tokenize(code)))
    with open(args.outpath, 'w', encoding='utf-8') as file:
        path = os.path.relpath("lib/lib.h", os.path.dirname(args.outpath)).replace(os.sep, "/")
        file.write(f'#include "{path}"\n')
        for toplevel_statement in parsed:
            c_output.emit_toplevel_statement(file, toplevel_statement)


main()
