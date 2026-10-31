FROM python:3.12-slim AS builder
WORKDIR /build
COPY pyproject.toml README.md LICENSE requirements-service.txt ./
COPY research/pyproject.toml research/pyproject.toml
COPY sentinel ./sentinel
COPY research/sentinel_research ./research/sentinel_research
RUN python -m pip install --no-cache-dir --constraint requirements-service.txt -r requirements-service.txt \
 && python -m pip wheel --no-cache-dir --no-deps --wheel-dir=/wheels . ./research

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 10001 sentinel && mkdir /data && chown sentinel:sentinel /data
WORKDIR /app
COPY --from=builder /wheels /wheels
COPY requirements-service.txt /tmp/requirements-service.txt
RUN python -m pip install --no-cache-dir --constraint /tmp/requirements-service.txt /wheels/mcp_runtime_sentinel-*.whl \
 && rm -rf /wheels /tmp/requirements-service.txt
USER 10001:10001
VOLUME ["/data"]
EXPOSE 8788
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import ssl,urllib.request; ctx=ssl.create_default_context(cafile='/certs/server.crt'); urllib.request.urlopen('https://localhost:8788/livez', context=ctx, timeout=2).read()" || exit 1
ENTRYPOINT ["python", "-m", "sentinel.cli"]

FROM python:3.12-slim AS mock
RUN useradd --create-home --uid 10001 sentinel
WORKDIR /app
COPY --from=builder /wheels /wheels
COPY requirements-service.txt /tmp/requirements-service.txt
RUN python -m pip install --no-cache-dir --constraint /tmp/requirements-service.txt -r /tmp/requirements-service.txt \
 && python -m pip install --no-cache-dir --constraint /tmp/requirements-service.txt /wheels/mcp_runtime_sentinel-*.whl /wheels/mcp_runtime_sentinel_research-*.whl \
 && rm -rf /wheels /tmp/requirements-service.txt
USER 10001:10001
EXPOSE 8790
ENTRYPOINT ["mcp-sentinel-mock"]
