#!/bin/bash
# The MyST engine (Jupyter Book 2) builds from within the project directory
# that contains myst.yml, so we run the build inside ./src.
cd "$(dirname "$0")/../src" && jupyter book build --html
