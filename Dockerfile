FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (layer cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and data files
COPY *.py ./
COPY personas.txt owasp-llm.txt ./

# Cloud Run sets $PORT; default to 8080 locally
ENV PORT=8080

# Run uvicorn bound to $PORT so Cloud Run can route traffic
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
