#!/usr/bin/env bash
sphinx-build -b html . build
python fixup.py
cp out/docs.html ../../assertpy.github.io
