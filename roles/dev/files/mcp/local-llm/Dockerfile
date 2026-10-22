FROM python:3.13-slim

ARG VERSION
RUN pip install --no-cache-dir "mcp-ollama-vllm==${VERSION}"

ENTRYPOINT ["mcp-ollama-vllm"]
