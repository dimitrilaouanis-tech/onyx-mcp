# Onyx MCP — stdio entrypoint for Glama health checks.
#
# Glama spins this container and talks JSON-RPC over stdio to verify the
# server starts and responds to MCP introspection (list_tools). Demo mode
# is on by default so the check passes with no external network.
FROM python:3.11-slim

WORKDIR /app

# OS deps for ddddocr (opencv runtime) and httpx-on-musl edge cases.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
        libglib2.0-0 \
        libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV ONYX_DEMO_MODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Stdio MCP entrypoint — what Glama exercises for introspection checks.
CMD ["python", "server.py"]
