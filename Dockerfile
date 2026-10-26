# syntax=docker/dockerfile:1

# Heliograph platform.
#
# Python only: the Tailwind stylesheet is built on a developer machine and
# committed to static/dist/, so the image needs no Node toolchain. That
# keeps it small and makes the Railway build the same shape as this one.

FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings.dev

WORKDIR /app

# curl is here for the container healthcheck. psycopg ships binary wheels,
# so no compiler or libpq headers are needed.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Dependencies first: this layer is cached until the pins actually change.
COPY requirements/ requirements/
RUN pip install -r requirements/dev.txt

COPY . .

# Run as a non-root user. The entrypoint needs to write collected static
# files and uploads, so those directories are created and handed over now.
RUN useradd --create-home --uid 1000 heliograph \
    && mkdir -p /app/staticfiles /app/mediafiles \
    && chown -R heliograph:heliograph /app
USER heliograph

EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]

# The production command. Compose overrides it with the dev server for
# local work; Railway uses the Procfile, which matches this.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", \
     "--workers", "3", "--threads", "2", "--timeout", "60", \
     "--access-logfile", "-", "--error-logfile", "-"]
