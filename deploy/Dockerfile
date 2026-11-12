# Required: an operator-verified official python:3.14.7-slim-bookworm digest.
# No floating-base fallback; build and retain a platform-specific wheelhouse.
ARG PYTHON_BASE=python@sha256:998acd06f485adfd6890e3e15a4b542543e0cf22ff904310095da328a5e3e561
FROM ${PYTHON_BASE} AS wheels
RUN apt-get update && apt-get install -y --no-install-recommends build-essential git && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY deploy/requirements-runtime.txt requirements.txt requirements-model.txt ./
RUN python -m pip wheel --wheel-dir /wheels -r requirements-runtime.txt
# The resolved wheel files + hashes are the offline installation contract.
RUN cd /wheels && sha256sum *.whl > SHA256SUMS

FROM ${PYTHON_BASE} AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home app
COPY --from=wheels /wheels /wheels
RUN cd /wheels && sha256sum -c SHA256SUMS && python -m pip install --no-index --find-links=/wheels /wheels/*.whl && python -m pip check \
    && python -m pip freeze > /runtime-packages.txt \
    && python -c "import numpy,SimpleITK,radiomics,cv2,scipy,sklearn"
WORKDIR /app
COPY src ./src
COPY service ./service
COPY migrations ./migrations
COPY scripts ./scripts
COPY tests ./tests
COPY docs ./docs
COPY pyradiomics_config.yaml ./
COPY deploy/requirements-storage-fixture.txt ./deploy/requirements-storage-fixture.txt
ENV ASSET_MANIFEST=/assets/manifest.json PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TMPDIR=/run/mini-nota \
    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS=1
USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["python", "-m", "service.backend"]

# CI-only executable dependencies for public process/JavaScript interoperability
# tests. Keep them out of the default release image and future compute runtime.
FROM runtime AS ci
USER root
RUN apt-get update && apt-get install -y --no-install-recommends nodejs procps && rm -rf /var/lib/apt/lists/* \
    && node --version && ps --version
USER 10001:10001

# A default build continues to produce the lean Python/native runtime.
FROM runtime AS release
