#!/bin/bash
# The reference answer, for Harbor's Oracle agent. It never enters the agent's image.
cat > /app/answer.json <<'EOF'
{
  "eitc": {
    "annual_amount": 0,
    "eligible": "unknown"
  },
  "explanation": "Reference answer.",
  "medicaid": {
    "eligible_members": [],
    "unknown_members": [
      "Imani"
    ]
  },
  "missing_information": [
    {
      "document": "pay_stubs",
      "member": "Imani"
    }
  ],
  "snap": {
    "eligible": "unknown",
    "monthly_benefit": 0
  },
  "wic": {
    "eligible_members": [],
    "unknown_members": []
  }
}
EOF
