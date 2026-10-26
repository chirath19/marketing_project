#!/bin/sh
# Prepare the database, then hand over to whatever command was given.
#
# Migrations run here rather than in a separate step so that `docker
# compose up` on a clean machine produces a working application without
# anyone having to remember a second command. On Railway the same work is
# done by the Procfile's release phase, which runs before the new version
# takes traffic.
set -e

echo "Waiting for PostgreSQL at ${POSTGRES_HOST:-db}:${POSTGRES_PORT:-5432}…"
until python -c "
import os, socket, sys
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

# WhiteNoise serves static files only when DEBUG is off; with the dev
# server Django's staticfiles app handles them from source instead.
if [ "${DJANGO_DEBUG}" != "True" ] && [ "${DJANGO_DEBUG}" != "true" ]; then
  python manage.py collectstatic --noinput
fi

exec "$@"
