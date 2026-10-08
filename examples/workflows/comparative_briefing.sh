#!/usr/bin/env bash
set -euo pipefail
cmg-agent --offline --pretty \
  --workflow comparative_briefing \
  --drugs Keytruda Opdivo \
  -q "Compare the labeled indications and major warnings of Keytruda and Opdivo, identify relevant clinical trials, summarize the supporting evidence, and prepare a cited briefing for medical-affairs review."
