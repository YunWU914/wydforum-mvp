#!/bin/sh
# Runs once per container start: prepare the database, then serve.
set -e

echo "==> Compiling translations"
python tools/build_locales.py

echo "==> Applying migrations"
python manage.py migrate --noinput

echo "==> Creating cache table (rate limits)"
python manage.py createcachetable

echo "==> Collecting static files"
python manage.py collectstatic --noinput

echo "==> Seeding default categories"
python manage.py seed_demo

# Demo users/topics (dev only: refuses when DEBUG=0 unless --force).
if [ "$SEED_DEMO" = "1" ]; then
  echo "==> Seeding demo content"
  python manage.py seed_demo --demo || true
fi

# Optional bootstrap admin: set DJANGO_SUPERUSER_USERNAME / _EMAIL / _PASSWORD.
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  echo "==> Ensuring admin user"
  python manage.py createsuperuser --noinput || echo "    (admin already exists)"
fi

echo "==> Starting: $*"
exec "$@"
