#!/bin/bash
cd "$HOME/LocalSecretLounge" || exit 1
source .venv/bin/activate
python app.py
