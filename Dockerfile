FROM node:22-alpine AS ui
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv
WORKDIR /service
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY app/ app/
COPY ml/ ml/
COPY migrations/ migrations/
COPY alembic.ini ./
COPY config/ config/
COPY artifacts/ artifacts/
COPY --from=ui /ui/dist frontend/dist
ENV PATH="/service/.venv/bin:$PATH" PYTHONUNBUFFERED=1
RUN useradd --uid 10001 --create-home router && chown -R router:router /service
USER router
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
