# The verifier's container, separate from the agent's: the answer key and the grading code are baked in here.
FROM python:3.12-slim
RUN pip install --no-cache-dir harbor-rewardkit==$rewardkit
COPY support/ /opt/ttune/
COPY truth.json /opt/ttune/truth.json
COPY criteria/ /tests/
COPY test.sh /tests/test.sh
RUN chmod +x /tests/test.sh
ENV PYTHONPATH=/opt/ttune
