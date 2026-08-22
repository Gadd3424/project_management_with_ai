FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml /app/
RUN pip install --no-cache-dir .
COPY . /app
RUN useradd --create-home app && chown -R app:app /app
USER app

