# syntax=docker/dockerfile:1
FROM python:3.14-slim

WORKDIR /app

# Package is stdlib-only; install just it (no dependencies).
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

# Mount your 3MF files at /data, e.g.:
#   docker run --rm -v "$PWD:/data" hictopswapper \
#     export /data/in.3mf --repeats 2 -o /data/out.3mf
WORKDIR /data
ENTRYPOINT ["hictopswapper"]
CMD ["--help"]
