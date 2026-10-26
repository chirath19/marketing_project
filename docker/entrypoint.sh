#!/bin/sh
# Prepare the database, then hand over to whatever command was given.
#
# Migrations run here rather than in a separate step so that both `docker
# compose up` on a clean machine and a Railway deploy (which builds this
# same Dockerfile rather than going through the Procfile/Nixpacks path)
# produce a working application without a separate release step.
set -e

echo "Waiting for PostgreSQL…"
until python -c "
import os, socket, sys
from urllib.parse import urlsplit

url = os.environ.get('DATABASE_URL')
if url:
    parts = urlsplit(url)
    host, port = parts.hostname, parts.port or 5432
else:
    # No DATABASE_URL set at all (shouldn't happen outside a misconfigured
    # environment) — fall back to the docker-compose service name.
    host = os.environ.get('POSTGRES_HOST', 'db')
    port = int(os.environ.get('POSTGRES_PORT', '5432'))

sock = socket.socket()
sock.settimeout(2)
try:
    sock.connect((host, port))
except OSError:
    sys.exit(1)
finally:
    sock.close()
" 2>/dev/null; do
  sleep 1
done
echo "PostgreSQL is up."

python manage.py migrate --noinput
python manage.py createcachetable
python manage.py seed_demo_data

# WhiteNoise serves static files only when DEBUG is off; with the dev
# server Django's staticfiles app handles them from source instead.
if [ "${DJANGO_DEBUG}" != "True" ] && [ "${DJANGO_DEBUG}" != "true" ]; then
  python manage.py collectstatic --noinput
fi

exec "$@"
