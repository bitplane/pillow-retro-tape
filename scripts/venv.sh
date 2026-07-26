#!/usr/bin/env bash

python3 -m venv .venv
source .venv/bin/activate

# pip >= 24 is needed to install the "LOAD $" console script; older
# vendored distlib chokes on the space in the entry point name.
python3 -m pip install --quiet --upgrade pip
