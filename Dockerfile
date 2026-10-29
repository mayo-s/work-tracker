# Work Tracker in a container, e.g. on a NAS: docker compose up -d --build (README, "Run in a container").

# 1. The frontend: TypeScript compiled to src/templates/static/js
FROM node:26-slim AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY src/templates src/templates
RUN npm run build

# 2. The Python packages of Pipfile.lock, without the dev packages
FROM python:3.15-slim AS requirements
RUN pip install --no-cache-dir pipenv
WORKDIR /build
COPY Pipfile Pipfile.lock ./
RUN pipenv requirements > requirements.txt

# 3. The app: gunicorn on port 8000, the database in /data
FROM python:3.15-slim
RUN apt-get update && apt-get install -y --no-install-recommends tzdata sqlite3 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=requirements /build/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src src
COPY --from=frontend /build/src/templates/static/js src/templates/static/js
RUN useradd --system --uid 1000 --home-dir /app work-tracker && mkdir /data && chown work-tracker /data
USER work-tracker
ENV WORK_TRACKER_DB=/data/work_tracker.db TZ=Europe/Berlin PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=1m --timeout=5s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
# --preload: the database is migrated once, before the workers start
CMD ["gunicorn", "src.app:create_app()", "--bind", "0.0.0.0:8000", "--workers", "2", "--preload", "--access-logfile", "-"]
