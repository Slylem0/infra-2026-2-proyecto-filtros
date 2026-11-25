# Trabajador

Capa HTTP delgada sobre el binario del motor, escrita en Python con solo la
biblioteca estándar. Recibe la imagen en crudo (`application/octet-stream`,
sin base64), invoca al motor y devuelve el resultado en crudo. Escucha en el
puerto **8000**.

## Endpoints

| Método y ruta | Respuesta |
|---|---|
| `POST /procesar?filtros=<cadena>` | `200` con el cuerpo de la imagen resultante y las cabeceras `X-Tiempo-Ms` y `X-Hilos` |
| `GET /healthz` | `200` si el proceso está vivo (liveness) |
| `GET /readyz` | `200` si el binario del motor existe y arranca; `503` si no (readiness) |

`filtros` es la lista separada por comas que entiende el motor (`gris`,
`caja`, `gaussiano`, `sobel`, `otsu`), por ejemplo
`gris,gaussiano,sobel,otsu`. El cuerpo es un PPM (P6) o un PGM (P5) binario y
la petición necesita `Content-Length` (máximo 64 MiB, ajustable con
`MAX_CUERPO`).

- `X-Tiempo-Ms`: milisegundos que tardó la invocación del motor, sin contar la
  transferencia por HTTP.
- `X-Hilos`: hilos de OpenMP con los que corrió, tomados de `OMP_NUM_THREADS`.

| Código | Cuándo |
|---|---|
| `400` | Falta `filtros`, hay un filtro desconocido, la cadena no se puede aplicar a esa imagen (por ejemplo `gris` sobre un canal) o el cuerpo no es un PPM/PGM válido. El cuerpo de la respuesta trae el motivo. |
| `411` / `413` | Falta `Content-Length` / el cuerpo supera `MAX_CUERPO`. |
| `501` | El filtro existe pero aún no está implementado en el motor. |
| `504` | El motor superó `TIEMPO_LIMITE` (120 s por defecto). |
| `500` | Cualquier otro fallo del motor. |

## Ejemplo con `curl`

```console
$ curl -s -X POST --data-binary @motor/tests/datos/entrada.ppm \
    "http://localhost:8000/procesar?filtros=gris" \
    -D - -o salida.pgm
HTTP/1.1 200 OK
Content-Type: application/octet-stream
Content-Length: 23
X-Tiempo-Ms: 1.951
X-Hilos: 2

$ curl -s -X POST --data-binary @motor/tests/datos/entrada.ppm \
    "http://localhost:8000/procesar?filtros=nada"
filtro desconocido: nada

$ curl -si http://localhost:8000/healthz | head -1
HTTP/1.1 200 OK
$ curl -si http://localhost:8000/readyz | head -1
HTTP/1.1 200 OK
```

Con `--data-binary` curl envía el archivo tal cual; con `-d` lo alteraría.

## Variables de entorno

| Variable | Por defecto | Qué hace |
|---|---|---|
| `OMP_NUM_THREADS` | núcleos visibles | Hilos del motor; se reporta en `X-Hilos`. En el clúster viene del ConfigMap `filtros-config`. |
| `PUERTO` | `8000` | Puerto de escucha. |
| `MOTOR_BIN` | `/app/motor` | Ruta del binario del motor. |
| `TIEMPO_LIMITE` | `120` | Segundos máximos por invocación del motor. |
| `MAX_CUERPO` | `67108864` | Bytes máximos del cuerpo. |

## La imagen

El contexto de construcción es la raíz del repositorio, como espera el
workflow de despliegue:

```console
$ docker build -f trabajador/Dockerfile -t trabajador:dev .
$ docker run --rm -p 8000:8000 -e OMP_NUM_THREADS=2 trabajador:dev
```

Es multi-etapa: la primera compila el motor con `-Wall -Wextra -Werror` y la
final solo lleva Python, `libgomp1`, el binario y `servidor.py`. Corre con el
usuario `10001:10001`, el mismo que fija el Deployment, y escribe sus
temporales solo en `/tmp`, de modo que funciona con el sistema de archivos
raíz en solo lectura.

## Sin Docker

```console
$ make -C motor motor
$ MOTOR_BIN=motor/motor python3 trabajador/servidor.py
```
