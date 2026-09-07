# One image, two roles: the FastAPI web service and the voice worker (see
# docker-compose.yml at the repo root — same image, different `command:`).
FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
