# The image a submitted method runs in during ranked evaluation.
#
# Build context (assembled by the evaluate workflow, never by the submitter):
#   compactbench/   the harness source at the commit being evaluated (trusted)
#   submission/     the submitted method.py and requirements.txt (untrusted)
#
# Dependencies install here, at build time, with network but without any secret.
# At run time the container gets no network except the model proxy, a read-only
# filesystem, no capabilities and an unprivileged user (see compactbench.sandbox).
FROM python:3.15-slim@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TIKTOKEN_CACHE_DIR=/opt/tiktoken

COPY compactbench /opt/compactbench
RUN pip install "/opt/compactbench[providers]" \
 && python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')" \
 && chmod -R a+rX /opt/tiktoken

COPY submission /opt/submission
RUN if [ -f /opt/submission/requirements.txt ]; then \
      pip install -r /opt/submission/requirements.txt; \
    fi

WORKDIR /opt/submission
USER 65534:65534
