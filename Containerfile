FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY feelinq/ feelinq/
RUN pip install --no-cache-dir .

CMD ["python", "-m", "feelinq.main"]
