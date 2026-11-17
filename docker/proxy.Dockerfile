# The model proxy for ranked evaluation. Built only from the harness — never from a
# submission. It is the sandbox's single network peer and holds the run's model key.
#
# Build context (assembled by the evaluate workflow from the harness at this commit):
#   requirements.txt   the ranked dependencies exported from uv.lock, with hashes
#   dist/*.whl         the compactbench wheel
# so nothing is resolved fresh from PyPI. The base image is pinned by digest
# (Dependabot keeps it current).
FROM python:3.15-slim@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

COPY requirements.txt /opt/requirements.txt
COPY dist/ /opt/dist/
RUN pip install --require-hashes --no-deps -r /opt/requirements.txt \
 && pip install --no-deps /opt/dist/*.whl

USER 65534:65534
EXPOSE 8080
ENTRYPOINT ["compactbench", "proxy", "--listen", "0.0.0.0:8080"]
