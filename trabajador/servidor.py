"""Trabajador HTTP: una capa delgada sobre el binario del motor.

Recibe la imagen en crudo (PPM o PGM binario) en el cuerpo de la petición,
la escribe en un archivo temporal, invoca al motor con la cadena de filtros y
devuelve el resultado en crudo. Solo usa la biblioteca estándar.

    POST /procesar?filtros=gris,gaussiano,sobel,otsu
    GET  /healthz   el proceso está vivo
    GET  /readyz    el binario del motor existe y responde
"""
import os
import signal
import subprocess
import tempfile
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

PUERTO = int(os.environ.get("PUERTO", "8000"))
MOTOR = os.environ.get("MOTOR_BIN", "/app/motor")
# Tiempo máximo de una invocación del motor, en segundos.
TIEMPO_LIMITE = float(os.environ.get("TIEMPO_LIMITE", "120"))
# Tamaño máximo del cuerpo: una imagen de 4096x4096 en color pesa 48 MiB.
MAX_CUERPO = int(os.environ.get("MAX_CUERPO", str(64 * 1024 * 1024)))

FILTROS_CONOCIDOS = {"gris", "caja", "gaussiano", "sobel", "otsu"}


def hilos():
    """Los hilos de OpenMP que usará el motor: lo que diga OMP_NUM_THREADS."""
    valor = os.environ.get("OMP_NUM_THREADS", "").strip()
    if valor.isdigit() and int(valor) > 0:
        return int(valor)
    return os.cpu_count() or 1


def motor_responde():
    """El binario existe y arranca. Sin argumentos el motor imprime el uso y
    sale con código 2, así que no procesa ninguna imagen."""
    if not (os.path.isfile(MOTOR) and os.access(MOTOR, os.X_OK)):
        return False
    try:
        r = subprocess.run([MOTOR], capture_output=True, timeout=2)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 2 and b"uso:" in r.stderr


class Manejador(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "trabajador"

    def log_message(self, formato, *args):
        print("%s %s" % (self.address_string(), formato % args), flush=True)

    def responder(self, codigo, cuerpo=b"", tipo="text/plain; charset=utf-8", extra=()):
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        for nombre, valor in extra:
            self.send_header(nombre, valor)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(cuerpo)

    def error(self, codigo, motivo, cerrar=False):
        if cerrar:
            # El cuerpo no se leyó: la conexión no se puede reutilizar.
            self.close_connection = True
        self.responder(codigo, (motivo + "\n").encode())

    def do_GET(self):
        ruta = urlsplit(self.path).path
        if ruta == "/healthz":
            self.responder(HTTPStatus.OK, b"ok\n")
        elif ruta == "/readyz":
            if motor_responde():
                self.responder(HTTPStatus.OK, b"listo\n")
            else:
                self.error(HTTPStatus.SERVICE_UNAVAILABLE, "el motor no responde")
        else:
            self.error(HTTPStatus.NOT_FOUND, "no existe " + ruta)

    do_HEAD = do_GET

    def do_POST(self):
        partes = urlsplit(self.path)
        if partes.path != "/procesar":
            return self.error(HTTPStatus.NOT_FOUND, "no existe " + partes.path, cerrar=True)

        consulta = parse_qs(partes.query)
        crudo = ",".join(consulta.get("filtros", []))
        filtros = [f for f in crudo.split(",") if f]
        if not filtros:
            return self.error(HTTPStatus.BAD_REQUEST,
                              "falta el parámetro filtros, por ejemplo ?filtros=gris,sobel",
                              cerrar=True)
        for f in filtros:
            if f not in FILTROS_CONOCIDOS:
                return self.error(HTTPStatus.BAD_REQUEST, "filtro desconocido: " + f,
                                  cerrar=True)

        largo = self.headers.get("Content-Length")
        if largo is None or not largo.isdigit():
            return self.error(HTTPStatus.LENGTH_REQUIRED,
                              "se requiere Content-Length", cerrar=True)
        largo = int(largo)
        if largo == 0:
            return self.error(HTTPStatus.BAD_REQUEST, "el cuerpo está vacío", cerrar=True)
        if largo > MAX_CUERPO:
            return self.error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                              "el cuerpo supera %d bytes" % MAX_CUERPO, cerrar=True)

        cuerpo = self.rfile.read(largo)
        if len(cuerpo) != largo:
            return self.error(HTTPStatus.BAD_REQUEST, "cuerpo incompleto", cerrar=True)

        # Los temporales van en TMPDIR (/tmp): en el clúster el resto del
        # sistema de archivos es de solo lectura.
        with tempfile.TemporaryDirectory(prefix="trabajador-") as trabajo:
            entrada = os.path.join(trabajo, "entrada")
            salida = os.path.join(trabajo, "salida")
            with open(entrada, "wb") as f:
                f.write(cuerpo)
            del cuerpo

            inicio = time.perf_counter()
            try:
                r = subprocess.run([MOTOR, ",".join(filtros), entrada, salida],
                                   capture_output=True, timeout=TIEMPO_LIMITE)
            except subprocess.TimeoutExpired:
                return self.error(HTTPStatus.GATEWAY_TIMEOUT, "el motor superó el tiempo límite")
            except OSError as e:
                return self.error(HTTPStatus.INTERNAL_SERVER_ERROR, "no se pudo ejecutar el motor: %s" % e)
            ms = (time.perf_counter() - inicio) * 1000.0

            mensaje = r.stderr.decode("utf-8", "replace").strip().replace(trabajo + os.sep, "")
            if r.returncode == 1 and "sin implementar" in mensaje:
                return self.error(HTTPStatus.NOT_IMPLEMENTED, mensaje)
            if r.returncode == 1:
                # El motor sale con 1 cuando rechaza la entrada: imagen
                # ilegible o cadena que no se puede aplicar.
                return self.error(HTTPStatus.BAD_REQUEST, mensaje)
            if r.returncode != 0:
                return self.error(HTTPStatus.INTERNAL_SERVER_ERROR,
                                  "el motor terminó con código %d: %s" % (r.returncode, mensaje))

            with open(salida, "rb") as f:
                resultado = f.read()

        self.responder(HTTPStatus.OK, resultado, "application/octet-stream", (
            ("X-Tiempo-Ms", "%.3f" % ms),
            ("X-Hilos", str(hilos())),
        ))


def terminar(*_):
    # Como PID 1 del contenedor, Python ignora SIGTERM si no hay manejador, y
    # Kubernetes esperaría el plazo completo antes de matarlo.
    raise KeyboardInterrupt


def main():
    signal.signal(signal.SIGTERM, terminar)
    servidor = ThreadingHTTPServer(("0.0.0.0", PUERTO), Manejador)
    servidor.daemon_threads = True
    print("trabajador escuchando en el puerto %d, motor %s" % (PUERTO, MOTOR), flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()
