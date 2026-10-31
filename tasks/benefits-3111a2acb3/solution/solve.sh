#!/bin/bash
# The reference answer, for Harbor's Oracle agent. It never enters the agent's image.
cat > /app/answer.json <<'EOF'
{
  "eitc": {
    "annual_amount": 7316.0,
    "eligible": true
  },
  "explanation": "Reference answer.",
  "medicaid": {
    "eligible_members": [
      "David",
      "Tomas",
      "Ana"
    ],
    "unknown_members": []
  },
  "missing_information": [],
  "snap": {
    "eligible": true,
    "monthly_benefit": 808.0
  },
  "wic": {
    "eligible_members": [
      "Ana"
    ],
    "unknown_members": []
  }
}
EOF
