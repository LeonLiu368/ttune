# The agent's container: the household's documents and a PolicyEngine calculator. No answers, no verifier code.
FROM python:3.12-slim
# tmux is for terminal agents such as Harbor's terminus-2, which can't install it here: the task has no network.
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils jq tmux \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir policyengine-us==2.50.1
COPY calc/ /opt/benefits-calc/
RUN printf '#!/bin/sh\nexec python /opt/benefits-calc/calc.py "$@"\n' > /usr/local/bin/benefits-calc \
    && chmod +x /usr/local/bin/benefits-calc \
    && benefits-calc --example > /tmp/example.json && benefits-calc /tmp/example.json > /dev/null && rm /tmp/example.json
RUN useradd --create-home caseworker
WORKDIR /app
COPY case/ /app/case/
RUN chown -R caseworker:caseworker /app
