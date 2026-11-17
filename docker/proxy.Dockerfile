# The model proxy for ranked evaluation. Built only from the harness — never from a
# submission. It is the sandbox's single network peer and holds the run's model key.
#
# Build context (assembled by the evaluate workflow from the harness at this commit):
#   requirements.txt   the ranked dependencies exported from uv.lock, with hashes
#   dist/*.whl         the compactbench wheel
# so nothing is resolved fresh from PyPI. The base image is pinned by digest
# (Dependabot keeps it current).
FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

COPY requirements.txt /opt/requirements.txt
COPY dist/ /opt/dist/
RUN pip install --require-hashes --no-deps -r /opt/requirements.txt \
 && pip install --no-deps /opt/dist/*.whl

USER 65534:65534
EXPOSE 8080
ENTRYPOINT ["compactbench", "proxy", "--listen", "0.0.0.0:8080"]
