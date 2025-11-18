FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .
COPY requirements-docker.txt .
COPY src/ ./src/
COPY tasks/ ./tasks/
COPY agentbeats/ ./agentbeats/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements-docker.txt
RUN pip install --no-cache-dir -e .

# Create reports directory
RUN mkdir -p reports

# Expose port for green agent
EXPOSE 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO
ENV HOST=0.0.0.0
ENV AGENT_PORT=8000
ENV PERSONAGYM_TASKS_DIR=/app/tasks
ENV PERSONAGYM_REPORTS_DIR=/app/reports

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import httpx; httpx.get('http://localhost:8000/health')"

# Run the green agent directly
CMD ["python", "agentbeats/green_agent.py"]
