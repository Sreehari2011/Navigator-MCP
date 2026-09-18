# --- Navigator MCP ------------------------------------------------------
# Autonomous browser control (stealth, captcha, vision, traffic inspection)
# behind the Model Context Protocol.
#
# Local stdio build (Claude Desktop / Cursor / VS Code):
#   docker build -t navigator-mcp .
#   docker run -i --rm --init navigator-mcp
#
# HTTP deployment (multi-client, API-key auth):
#   docker run -p 8765:8765 -e NAVIGATOR_API_KEYS=sk-your-key navigator-mcp \
#       --transport http --host 0.0.0.0 --port 8765
#
# Headful mode (captchas / anti-bot): connect to the VNC on port 5901 (no VNC
# password in the example — put this behind a firewall or add one).

FROM python:3.12-slim

# Chromium runtime dependencies + Xvfb/x11vnc for headful stealth sessions
RUN apt-get update && apt-get install -y --no-install-recommends \
        chromium \
        xvfb \
        x11vnc \
        fluxbox \
        fonts-liberation \
        fonts-noto-color-emoji \
        libnss3 \
        libxss1 \
        libasound2 \
        libgtk-3-0 \
        tini \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY navigator_mcp ./navigator_mcp
RUN pip install --no-cache-dir .

# Workspace for profiles / downloads / usage data
ENV NAVIGATOR_WORKSPACE=/data \
    NAVIGATOR_BROWSER_CHANNEL=chromium \
    NAVIGATOR_HEADLESS=true
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8765 5901 9222

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD []
