FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Build-time collection uses only development defaults, no DB or secrets.
RUN DJANGO_DEBUG=true python manage.py collectstatic --noinput \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home app \
    && mkdir -p /app/media && chown app:app /app/media
USER app
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "60", "--no-control-socket", "--forwarded-allow-ips", "", "config.wsgi:application"]
