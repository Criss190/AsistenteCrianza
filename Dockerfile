FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements-deploy.txt .
RUN pip install --no-cache-dir -r requirements-deploy.txt

COPY . .

EXPOSE 8080

CMD ["sh", "-c", "exec gunicorn main:app --bind 0.0.0.0:${PORT:-8080} --workers 1 --timeout 120"]
