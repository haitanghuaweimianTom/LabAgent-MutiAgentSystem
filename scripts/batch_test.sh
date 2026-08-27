#!/bin/bash
set -e
cd "/home/tomgame/projects/MathModel-MutiAgentSystem"
export MINIMAX_API_KEY="sk-cp-sxw2xgI88b-tHAo-L-BZtRojvuH0-UlbatdZnyukzPpflQW0_wRCmKIHTbsgUL7ZZ5gB8-xvVD0BG9IZf-cZCATs57gpm7bs-dlIYS0VbOXA4MyFf2AZrSM"
export LLM_MAX_CONTEXT_LENGTH=500000
export LLM_AUTO_COMPRESS_RATIO=0.9
export PYTHONPATH=/home/tomgame/projects/MathModel-MutiAgentSystem
python3 scripts/test_all_templates.py 2>&1 | tail -50