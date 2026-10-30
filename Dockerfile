FROM python:3.12-slim AS builder
WORKDIR /build
COPY pyproject.toml README.md LICENSE requirements-service.txt ./
COPY sentinel ./sentinel
RUN python -m pip install --no-cache-dir --constraint requirements-service.txt -r requirements-service.txt \
 && python -m pip wheel --no-cache-dir --no-deps --wheel-dir=/wheels .

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 10001 sentinel && mkdir /data && chown sentinel:sentinel /data
WORKDIR /app
COPY --from=builder /wheels /wheels
COPY requirements-service.txt /tmp/requirements-service.txt
RUN python -m pip install --no-cache-dir --constraint /tmp/requirements-service.txt /wheels/*.whl \
 && rm -rf /wheels /tmp/requirements-service.txt
USER 10001:10001
VOLUME ["/data"]
EXPOSE 8788
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import ssl,urllib.request; urllib.request.urlopen('https://127.0.0.1:8788/livez', context=ssl._create_unverified_context(), timeout=2).read()" || exit 1
ENTRYPOINT ["python", "-m", "sentinel.cli"]
