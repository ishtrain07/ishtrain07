# Hugging Face Space (Docker SDK): builds Heritage Plate straight from GitHub.
# Set NEBIUS_API_KEY (and optionally LANGSMITH_API_KEY) under Space settings -> Secrets.
# After pushing new code to GitHub, use Settings -> "Factory rebuild" to pick it up.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
ARG BRANCH=claude/stoic-wozniak-8ie5mb
RUN git clone --depth 1 -b "$BRANCH" https://github.com/ishtrain07/ishtrain07.git /src

WORKDIR /src/heritage-plate
RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONUNBUFFERED=1 PORT=7860 TRUST_PROXY=1 RATE_LIMIT=100 MAX_CALLS_PER_HOUR=600 \
    LLM_TIMEOUT_ULTRA_S=40 LLM_DEADLINE_S=55 \
    LANGSMITH_ENDPOINT=https://apac.api.smith.langchain.com LANGSMITH_PROJECT=heritage-plate

# Spaces run as user 1000.
RUN useradd -m -u 1000 user && chown -R user /src
USER user
EXPOSE 7860
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
