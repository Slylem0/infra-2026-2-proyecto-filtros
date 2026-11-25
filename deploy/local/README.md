# El servicio en local con Docker Compose

Una sola orden construye las imágenes, genera el lote y lo procesa con
varios trabajadores:

```console
$ cd deploy/local
$ docker compose up --build --scale trabajador=4
```

Desde la raíz del repositorio es lo mismo con
`docker compose -f deploy/local/docker-compose.yml up --build --scale trabajador=4`.

## Qué pasa

1. **`lote-init`** compila el generador del motor, deja 64 PPM de 1024x1024
   en el volumen `lote` (`/datos/entrada`), vacía `/datos/salida` y termina.
   Si el lote ya está completo no lo regenera.
2. **`trabajador`** arranca N réplicas (`--scale`). Cada una tiene 2 CPU y
   `OMP_NUM_THREADS=2`, como en el clúster, y el healthcheck espera a que
   `/readyz` responda.
3. **`despachador`** espera a que el lote esté listo y los trabajadores
   sanos, procesa el lote contra `http://trabajador:8000` y termina. El DNS de
   Compose reparte las peticiones entre las réplicas.

Al terminar, el despachador imprime la fila de la medición y la agrega a
`mediciones/servicio.csv` del repositorio:

```text
despachador-1  | entorno,trabajadores,concurrencia,imagenes,segundos
despachador-1  | local,4,8,64,0.962
despachador-1  | despachador: 66.54 imágenes por segundo
```

Los trabajadores siguen corriendo después: `Ctrl+C` para cerrar, y
`docker compose down` para borrar los contenedores (con `-v` también se borra
el lote). No uses `--abort-on-container-exit`: corta todo cuando termina
`lote-init`, antes de que empiece el despachador.

## Variables

Se pasan en el entorno de la orden, por ejemplo
`CONCURRENCIA=16 TRABAJADORES=2 docker compose up --build --scale trabajador=2`.

| Variable | Por defecto | Qué hace |
|---|---|---|
| `FILTROS` | `gris,gaussiano,sobel,otsu` | Cadena de filtros del lote. |
| `CONCURRENCIA` | `8` | Peticiones simultáneas del despachador. |
| `OMP_NUM_THREADS` | `2` | Hilos del motor en cada trabajador. |
| `TRABAJADORES` | `4` | Etiqueta de la columna `trabajadores`. Compose no le dice al despachador cuántas réplicas hay: ponla igual que `--scale`. |

## El lote

`lote-init` genera una imagen con `motor/bench/generar` y la copia 64 veces:
el generador es determinista, así que las copias son idénticas a generar 64
veces. Se puede cambiar con `LOTE_IMAGENES`, `LOTE_ANCHO` y `LOTE_ALTO` en el
servicio `lote-init`.

Para mirar las salidas:

```console
$ docker run --rm -v filtros_lote:/datos alpine ls -l /datos/salida
```
