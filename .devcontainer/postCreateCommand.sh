#!/usr/bin/env sh

set -eux

# create poetry venvdir under projectdir
poetry config virtualenvs.in-project true
poetry install

# Install typos cli
curl -sLO https://raw.githubusercontent.com/crate-ci/gh-install/master/v1/install.sh
sh install.sh -s -- --git crate-ci/typos --to ~/.local/bin --target x86_64-unknown-linux-musl
rm install.sh
