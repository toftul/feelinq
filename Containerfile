FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY feelinq/ feelinq/

CMD ["python", "-m", "feelinq.main"]
