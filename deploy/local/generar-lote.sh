#!/bin/sh
# Deja listo el volumen del lote: LOTE_IMAGENES PPM de LOTE_ANCHOxLOTE_ALTO en
# /datos/entrada y un /datos/salida escribible. Si el lote ya está completo no
# lo regenera, así que repetir `docker compose up` es barato.
set -eu

N="${LOTE_IMAGENES:-64}"
ANCHO="${LOTE_ANCHO:-1024}"
ALTO="${LOTE_ALTO:-1024}"
UID_APP=10001

mkdir -p /datos/entrada /datos/salida

existentes=$(find /datos/entrada -maxdepth 1 -name 'img-*.ppm' | wc -l)
if [ "$existentes" -eq "$N" ] && [ -z "$(find /datos/entrada -maxdepth 1 -name 'img-*.ppm' -size 0)" ]; then
    echo "lote: ya están las $N imágenes de ${ANCHO}x${ALTO}"
else
    echo "lote: generando $N imágenes de ${ANCHO}x${ALTO}"
    rm -f /datos/entrada/img-*.ppm
    # El generador produce siempre el mismo archivo: se genera una vez y se
    # copia, así el lote cuesta una generación y no 64.
    generar /datos/entrada/img-001.ppm "$ANCHO" "$ALTO" > /dev/null
    i=2
    while [ "$i" -le "$N" ]; do
        cp /datos/entrada/img-001.ppm "/datos/entrada/img-$(printf '%03d' "$i").ppm"
        i=$((i + 1))
    done
    echo "lote: listo"
fi

# Los resultados de una corrida anterior no cuentan para la siguiente.
rm -f /datos/salida/*

# Tabla de mediciones, montada desde el repositorio: la escribe el despachador,
# que no es root.
if [ -d /mediciones ]; then
    touch /mediciones/servicio.csv
    chmod a+rw /mediciones/servicio.csv
fi

chown -R "$UID_APP:$UID_APP" /datos
