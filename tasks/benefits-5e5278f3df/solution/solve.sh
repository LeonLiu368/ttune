#!/bin/bash
# The reference answer, for Harbor's Oracle agent. It never enters the agent's image.
cat > /app/answer.json <<'EOF'
{
  "eitc": {
    "annual_amount": 3855.84,
    "eligible": true
  },
  "explanation": "Reference answer.",
  "medicaid": {
    "eligible_members": [
      "Jasmine",
      "Gloria"
    ],
    "unknown_members": []
  },
  "missing_information": [],
  "snap": {
    "eligible": true,
    "monthly_benefit": 66.0
  },
  "wic": {
    "eligible_members": [
      "Jasmine",
      "Gloria"
    ],
    "unknown_members": []
  }
}
EOF
