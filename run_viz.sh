#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
python src/viz_dashboard.py
