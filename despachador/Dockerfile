# Contexto de construcción: la raíz del repositorio.
#   docker build -f despachador/Dockerfile -t despachador:dev .
FROM python:3.12-slim-bookworm

RUN groupadd --gid 10001 despachador \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin despachador

WORKDIR /app
COPY despachador/despachador.py /app/despachador.py

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER 10001:10001
CMD ["python", "/app/despachador.py"]
