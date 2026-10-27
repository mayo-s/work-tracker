# work-tracker

Simple tracker for daily tasks: working hours, overtime balance, PTO and task entries for the
monthly work report. A Falcon REST API with a small browser frontend, backed by SQLite, run locally.

> Work in progress — the calculation rules are being built first; API and frontend follow.

## Requirements

- Python 3.15
- [Pipenv](https://pipenv.pypa.io/)

## Setup

```shell
pipenv install --dev
```

## Tests and code quality

```shell
pipenv run pytest
pipenv run flake8 --count --exit-zero --radon-max-cc 6 --radon-no-assert --max-line-length=127 \
  --statistics --exclude=.idea,.venv,test,.terraform --extend-ignore=E203,W503,ANN101,ANN102
```

## Project layout

| Path | Contents |
|---|---|
| `src/lib` | Calculation rules: durations, breaks, holidays, targets, overtime, PTO |
| `src/models` | Pydantic models |
| `src/modules` | Features: storage, import, days, entries, reports, review |
| `src/utils` | Shared helpers |
| `src/defaultresources` | Default resource |
| `src/templates` | Frontend pages (TypeScript) |
| `src/tests` | Tests, mirroring the packages above |
