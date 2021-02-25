%.c: %.code $(wildcard compiler/*.py)
	python3 -m compiler < $< > $@
