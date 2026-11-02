#!/bin/sh
# Deploy to AWS Lambda (README, "Deploy to AWS"): ./deploy/zappa.sh dev deploy the first time, then
# ./deploy/zappa.sh dev update (or prod). zappa copies the packages of the active virtualenv into the package on their
# own, apart from the project files (excluding the `.venv` folder does not keep them out), so it runs in a virtualenv
# holding only what the app needs (not the tests' moto, pytest, …), outside the project, with the compiled frontend.
# Needs the deploying user's AWS credentials (e.g. awsume).
set -e
case "$1" in
  dev|prod) stage="$1" ;;
  *) echo "Usage: $0 dev|prod [deploy|update|status|tail|…]" >&2; exit 2 ;;
esac
cd "$(dirname "$0")/.."
venv="${XDG_CACHE_HOME:-$HOME/.cache}/work-tracker/deploy-venv"
npm run build
python3.14 -m venv "$venv"
PIPENV_VERBOSITY=-1 PIPENV_DONT_LOAD_ENV=1 pipenv requirements > "$venv/requirements.txt"
"$venv/bin/pip" install --quiet --upgrade pip
"$venv/bin/pip" install --quiet -r "$venv/requirements.txt" zappa==0.63.0
. "$venv/bin/activate"
zappa "${2:-update}" "$stage"
