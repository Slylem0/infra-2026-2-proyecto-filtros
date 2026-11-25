# Despachador

Reparte un lote de imágenes entre los trabajadores y mide cuánto tarda. Solo
usa la biblioteca estándar de Python.

Siempre pide a **una sola dirección**, `URL_TRABAJADOR`
(`http://trabajador:8000`). Cuántos trabajadores hay detrás lo decide la red:
el Service en Kubernetes o el DNS de Compose. Subir o bajar réplicas
(`kubectl scale`, `docker compose up --scale trabajador=N`) no cambia ni una
línea del despachador.

## Qué hace

1. Lee los `.ppm` y `.pgm` de `DIR_ENTRADA` (`/datos/entrada`).
2. Envía cada uno a `POST /procesar?filtros=<FILTROS>`, con hasta
   `CONCURRENCIA` peticiones en vuelo (`concurrent.futures`).
3. Escribe cada resultado en `DIR_SALIDA` (`/datos/salida`) con el mismo
   nombre y la extensión que corresponda (`.pgm` o `.ppm`).
4. Si todas salieron bien, agrega una fila a `RUTA_CSV` y la imprime en el
   registro, que es lo que se lee cuando corre como Job.

Si una imagen falla, termina con código 1 y **no** registra la medición: un
tiempo de un lote incompleto no sirve. Los fallos de conexión y los códigos
502, 503 y 504 se reintentan (`REINTENTOS`, 2 por defecto). El resto no: un
4xx, un 501 (filtro sin implementar) o un 500 darían la misma respuesta.

Cada petición abre una conexión nueva. El Service de Kubernetes balancea por
conexión, así que con una conexión larga por hilo cada hilo quedaría pegado a
una réplica durante todo el lote.

## Variables de entorno

| Variable | Por defecto | Qué hace |
|---|---|---|
| `URL_TRABAJADOR` | `http://trabajador:8000` | Dirección única de los trabajadores. |
| `FILTROS` | `gris,gaussiano,sobel,otsu` | Cadena de filtros. En el clúster viene del ConfigMap. |
| `CONCURRENCIA` | `8` | Peticiones simultáneas máximas. También viene del ConfigMap. |
| `DIR_ENTRADA` | `/datos/entrada` | Imágenes del lote. |
| `DIR_SALIDA` | `/datos/salida` | Resultados. |
| `RUTA_CSV` | `/datos/servicio.csv` | Tabla de mediciones; se agrega una fila por corrida. |
| `ENTORNO` | `local` | Valor de la columna `entorno` (`local`, `gke`...). |
| `TRABAJADORES` | `n/d` | Valor de la columna `trabajadores`. El despachador no puede contar las réplicas, así que quien lanza la corrida lo declara. |
| `TIEMPO_PETICION` | `120` | Segundos máximos por petición. |
| `REINTENTOS` | `2` | Reintentos por imagen ante 502, 503, 504 o fallos de conexión. |

## La tabla de mediciones

```csv
entorno,trabajadores,concurrencia,imagenes,segundos
local,1,8,12,0.082
```

En Compose se monta `mediciones/` y `RUTA_CSV` apunta a
`mediciones/servicio.csv`. En el clúster el archivo queda en el volumen
`/datos` y la fila también sale en el registro del Job
(`kubectl -n filtros logs job/despachador`).

## La imagen

```console
$ docker build -f despachador/Dockerfile -t despachador:dev .
$ docker run --rm --network host -v "$PWD/datos:/datos" \
    -e URL_TRABAJADOR=http://localhost:8000 -e TRABAJADORES=1 despachador:dev
```

Corre con el usuario `10001:10001` y solo escribe en `/datos`, así que
funciona con el sistema de archivos raíz de solo lectura. El directorio
montado tiene que ser escribible por ese usuario.
