Commands:

```
python3 -m venv env
. env/bin/activate
pip install more_itertools mypy isort pyflakes
./test
isort compiler
mypy --strict compiler
pyflakes compiler
```

To compile `foo.code` into executable `build/foo`, run `make build/foo`
