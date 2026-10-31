#!/bin/bash
# Scores /app/answer.json (copied in by Harbor) into /logs/verifier/reward.json. Offline: everything is in the image.
mkdir -p /logs/verifier
rewardkit /tests --workspace /app --output /logs/verifier/reward.json
