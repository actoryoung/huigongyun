FROM python:3.12-slim

WORKDIR /app

# Install build deps and runtime requirements
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Create non-root user (uid/gid 1000)
RUN set -eux \
    && groupadd -g 1000 appgroup \
    && useradd -r -u 1000 -g appgroup -m -d /home/appuser appuser

# Copy project
COPY . /app

# Ensure app directory owned by appuser
RUN chown -R appuser:appgroup /app

ENV PYTHONUNBUFFERED=1 \
    HOME=/home/appuser

USER appuser

# Default command runs the demo webapp. In production use a proper WSGI server.
CMD ["python", "-c", "from src.webapp import main; main()"]
