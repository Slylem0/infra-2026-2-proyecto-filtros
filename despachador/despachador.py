"""Despachador: reparte un lote de imágenes entre los trabajadores.

Lee todas las imágenes de DIR_ENTRADA, las envía a URL_TRABAJADOR con varias
peticiones en vuelo, escribe los resultados en DIR_SALIDA y agrega una fila a
la tabla de mediciones del servicio.

Siempre pide a una sola dirección. Cuántos trabajadores hay detrás lo decide
la red (el Service de Kubernetes o el DNS de Compose), así que subir o bajar
réplicas no toca este archivo. Solo usa la biblioteca estándar.
"""
import csv
import http.client
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urlsplit

URL_TRABAJADOR = os.environ.get("URL_TRABAJADOR", "http://trabajador:8000")
FILTROS = os.environ.get("FILTROS", "gris,gaussiano,sobel,otsu")
CONCURRENCIA = int(os.environ.get("CONCURRENCIA", "8"))
DIR_ENTRADA = os.environ.get("DIR_ENTRADA", "/datos/entrada")
DIR_SALIDA = os.environ.get("DIR_SALIDA", "/datos/salida")
# Dónde se agrega la fila de la medición. En Compose es mediciones/servicio.csv
# del repositorio, montado en el contenedor.
RUTA_CSV = os.environ.get("RUTA_CSV", "/datos/servicio.csv")
# Etiquetas de la fila. El despachador no puede saber cuántas réplicas hay
# detrás de la dirección, así que quien lanza la corrida las declara.
ENTORNO = os.environ.get("ENTORNO", "local")
TRABAJADORES = os.environ.get("TRABAJADORES", "n/d")
TIEMPO_PETICION = float(os.environ.get("TIEMPO_PETICION", "120"))
REINTENTOS = int(os.environ.get("REINTENTOS", "2"))

COLUMNAS = ["entorno", "trabajadores", "concurrencia", "imagenes", "segundos"]


def listar_entrada():
    if not os.path.isdir(DIR_ENTRADA):
        raise SystemExit("despachador: no existe el directorio de entrada " + DIR_ENTRADA)
    nombres = sorted(n for n in os.listdir(DIR_ENTRADA)
                     if n.lower().endswith((".ppm", ".pgm")))
    if not nombres:
        raise SystemExit("despachador: no hay .ppm ni .pgm en " + DIR_ENTRADA)
    return nombres


def enviar(cuerpo):
    """Un POST a /procesar sobre una conexión nueva.

    El Service de Kubernetes balancea por conexión, no por petición. Una
    conexión por petición hace que cada imagen pueda caer en una réplica
    distinta; con una conexión larga por hilo, cada hilo quedaría pegado a la
    misma réplica todo el lote.
    """
    destino = urlsplit(URL_TRABAJADOR)
    conexion = http.client.HTTPConnection(destino.hostname, destino.port or 80,
                                          timeout=TIEMPO_PETICION)
    try:
        conexion.request("POST", "/procesar?filtros=" + quote(FILTROS, safe=","), body=cuerpo,
                         headers={"Content-Type": "application/octet-stream",
                                  "Connection": "close"})
        r = conexion.getresponse()
        return r.status, r.read()
    finally:
        conexion.close()


def procesar(nombre):
    """Procesa una imagen y devuelve (nombre, error). error es None si salió bien."""
    with open(os.path.join(DIR_ENTRADA, nombre), "rb") as f:
        cuerpo = f.read()
    ultimo = ""
    for intento in range(REINTENTOS + 1):
        try:
            estado, datos = enviar(cuerpo)
        except (OSError, http.client.HTTPException) as e:
            # El trabajador aún no escucha, se reinició o la red falló.
            ultimo = "%s: %s" % (type(e).__name__, e)
            time.sleep(0.5 * (intento + 1))
            continue
        if estado == 200:
            extension = ".pgm" if datos[:2] == b"P5" else ".ppm"
            destino = os.path.join(DIR_SALIDA, os.path.splitext(nombre)[0] + extension)
            with open(destino, "wb") as f:
                f.write(datos)
            return nombre, None
        ultimo = "HTTP %d: %s" % (estado, datos.decode("utf-8", "replace").strip())
        if estado < 500:
            # Un 4xx es un problema de la imagen o de la cadena: repetirlo
            # daría la misma respuesta.
            break
        time.sleep(0.5 * (intento + 1))
    return nombre, ultimo


def main():
    if CONCURRENCIA < 1:
        raise SystemExit("despachador: CONCURRENCIA debe ser al menos 1")
    nombres = listar_entrada()
    os.makedirs(DIR_SALIDA, exist_ok=True)
    print("despachador: %d imágenes, filtros %s, concurrencia %d, destino %s"
          % (len(nombres), FILTROS, CONCURRENCIA, URL_TRABAJADOR), flush=True)

    inicio = time.perf_counter()
    fallos = []
    with ThreadPoolExecutor(max_workers=CONCURRENCIA) as pool:
        for nombre, error in pool.map(procesar, nombres):
            if error is not None:
                fallos.append((nombre, error))
                print("  FALLA %s: %s" % (nombre, error), file=sys.stderr, flush=True)
    segundos = time.perf_counter() - inicio

    if fallos:
        print("despachador: fallaron %d de %d imágenes; no se registra la medición"
              % (len(fallos), len(nombres)), file=sys.stderr)
        return 1

    fila = [ENTORNO, TRABAJADORES, CONCURRENCIA, len(nombres), "%.3f" % segundos]
    nuevo = not os.path.exists(RUTA_CSV) or os.path.getsize(RUTA_CSV) == 0
    with open(RUTA_CSV, "a", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        if nuevo:
            w.writerow(COLUMNAS)
        w.writerow(fila)
    # También al registro, que es lo que se lee cuando el Job corre en el clúster.
    print(",".join(COLUMNAS))
    print(",".join(str(v) for v in fila), flush=True)
    print("despachador: %.2f imágenes por segundo" % (len(nombres) / segundos))
    return 0


if __name__ == "__main__":
    sys.exit(main())
