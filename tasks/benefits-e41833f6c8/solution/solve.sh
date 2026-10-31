#!/bin/bash
# The reference answer, for Harbor's Oracle agent. It never enters the agent's image.
cat > /app/answer.json <<'EOF'
{
  "eitc": {
    "annual_amount": 5091.8,
    "eligible": true
  },
  "explanation": "Reference answer.",
  "medicaid": {
    "eligible_members": [
      "Fatima",
      "Mariana",
      "Omar",
      "Kevin",
      "Tariq"
    ],
    "unknown_members": []
  },
  "missing_information": [
    {
      "document": "lease_rent_page",
      "member": null
    }
  ],
  "snap": {
    "eligible": true,
    "monthly_benefit": 0
  },
  "wic": {
    "eligible_members": [
      "Tariq"
    ],
    "unknown_members": []
  }
}
EOF
