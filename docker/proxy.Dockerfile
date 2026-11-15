# The model proxy for ranked evaluation. Built only from the harness source —
# never from a submission. It is the sandbox's single network peer.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

COPY compactbench /opt/compactbench
RUN pip install "/opt/compactbench[ranked]"

USER 65534:65534
EXPOSE 8080
ENTRYPOINT ["compactbench", "proxy", "--listen", "0.0.0.0:8080"]
