FROM python:3.12-slim

WORKDIR /app

# Install build deps and runtime requirements
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy project
COPY . /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src:$PYTHONPATH

# Default command runs the demo webapp. In production use a proper WSGI server.
CMD ["python", "-c", "from huigongyun.webapp import main; main()"]
