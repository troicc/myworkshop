.PHONY: install test lint demo run doctor clean

install:
	python -m pip install -e ".[dev]"

test:
	pytest -q

lint:
	ruff check .

demo:
	python -m app.cli demo

run:
	python -m app.cli run

doctor:
	python -m app.cli doctor

clean:
	rm -rf workspace .pytest_cache .ruff_cache
