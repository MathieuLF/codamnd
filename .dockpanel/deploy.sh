#!/usr/bin/env bash
set -euo pipefail

test -f docs/index.html

install -d public
cp -a docs/. public/
