# Contexto de construcción: la raíz del repositorio.
#   docker build -f trabajador/Dockerfile -t trabajador:dev .

# Etapa 1: compilar el motor. Parte de la misma base que la imagen final, así
# la compilación y la ejecución usan la misma glibc y libgomp.
FROM python:3.12-slim-bookworm AS motor
RUN apt-get update \
    && apt-get install -y --no-install-recommends g++ make \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY motor/ motor/
RUN make -C motor motor CXXFLAGS="-std=c++17 -O2 -Wall -Wextra -Werror -fopenmp"

# Etapa 2: imagen final. Solo el intérprete de Python, el runtime de OpenMP,
# el binario del motor y el servidor.
FROM python:3.12-slim-bookworm
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 trabajador \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin trabajador

WORKDIR /app
COPY --from=motor /src/motor/motor /app/motor
COPY trabajador/servidor.py /app/servidor.py

ENV MOTOR_BIN=/app/motor \
    PUERTO=8000 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER 10001:10001
EXPOSE 8000
CMD ["python", "/app/servidor.py"]
