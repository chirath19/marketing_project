release: python manage.py migrate --noinput && python manage.py createcachetable
web: gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers ${WEB_CONCURRENCY:-3} --threads 2 --timeout 60 --access-logfile - --error-logfile -
