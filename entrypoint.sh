#!/bin/sh
set -e

echo "Aguardando PostgreSQL em ${DB_HOST:-db}:${DB_PORT:-5432}..."
while ! nc -z "${DB_HOST:-db}" "${DB_PORT:-5432}"; do
  sleep 0.5
done
echo "PostgreSQL pronto!"

echo "Aplicando migrações no banco de dados..."
python manage.py migrate --noinput

echo "Coletando arquivos estáticos..."
python manage.py collectstatic --noinput

exec "$@"
