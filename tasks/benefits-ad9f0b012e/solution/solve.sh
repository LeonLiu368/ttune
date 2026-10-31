#!/bin/bash
# The reference answer, for Harbor's Oracle agent. It never enters the agent's image.
cat > /app/answer.json <<'EOF'
{
  "eitc": {
    "annual_amount": 4427.0,
    "eligible": true
  },
  "explanation": "Reference answer.",
  "medicaid": {
    "eligible_members": [
      "Abigail"
    ],
    "unknown_members": []
  },
  "missing_information": [
    {
      "document": "childcare_receipt",
      "member": null
    }
  ],
  "snap": {
    "eligible": true,
    "monthly_benefit": 562.0
  },
  "wic": {
    "eligible_members": [],
    "unknown_members": []
  }
}
EOF
