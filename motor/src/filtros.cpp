#include "filtros.hpp"

#include <cmath>
#include <stdexcept>

Imagen gris_secuencial(const Imagen& e) {
    if (e.canales != 3) throw std::runtime_error("gris espera una imagen de tres canales");
    Imagen s;
    s.ancho = e.ancho;
    s.alto = e.alto;
    s.canales = 1;
    s.datos.resize(static_cast<std::size_t>(e.ancho) * e.alto);
    for (int y = 0; y < e.alto; ++y) {
        for (int x = 0; x < e.ancho; ++x) {
            const double v = 0.299 * e.en(x, y, 0) + 0.587 * e.en(x, y, 1) + 0.114 * e.en(x, y, 2);
            s.poner(x, y, 0, redondear(v));
        }
    }
    return s;
}

Imagen gris_paralelo(const Imagen& e) {
    if (e.canales != 3) throw std::runtime_error("gris espera una imagen de tres canales");
    Imagen s;
    s.ancho = e.ancho;
    s.alto = e.alto;
    s.canales = 1;
    s.datos.resize(static_cast<std::size_t>(e.ancho) * e.alto);
    // Cada fila es independiente de las demás: no hay nada que compartir
    // entre hilos ni dependencias entre iteraciones.
    #pragma omp parallel for schedule(static)
    for (int y = 0; y < e.alto; ++y) {
        for (int x = 0; x < e.ancho; ++x) {
            const double v = 0.299 * e.en(x, y, 0) + 0.587 * e.en(x, y, 1) + 0.114 * e.en(x, y, 2);
            s.poner(x, y, 0, redondear(v));
        }
    }
    return s;
}

namespace {

// El promedio de la vecindad de 3x3 de un canal, con las coordenadas
// recortadas al rectángulo de la imagen.
double promedio_vecindad(const Imagen& e, int x, int y, int c) {
    double suma = 0.0;
    for (int j = -1; j <= 1; ++j) {
        const int fila = recortar(y + j, e.alto);
        for (int i = -1; i <= 1; ++i) {
            suma += e.en(recortar(x + i, e.ancho), fila, c);
        }
    }
    return suma / 9.0;
}

}  // namespace

Imagen caja_secuencial(const Imagen& e) {
    Imagen s = e;
    for (int y = 0; y < e.alto; ++y) {
        for (int x = 0; x < e.ancho; ++x) {
            for (int c = 0; c < e.canales; ++c) {
                s.poner(x, y, c, redondear(promedio_vecindad(e, x, y, c)));
            }
        }
    }
    return s;
}

Imagen caja_paralelo(const Imagen& e) {
    Imagen s = e;
    // El ciclo externo recorre filas y el interno columnas, que es el orden
    // en que la imagen está en memoria. Repartir por filas deja a cada hilo
    // con una banda contigua.
    #pragma omp parallel for schedule(static)
    for (int y = 0; y < e.alto; ++y) {
        for (int x = 0; x < e.ancho; ++x) {
            for (int c = 0; c < e.canales; ++c) {
                s.poner(x, y, c, redondear(promedio_vecindad(e, x, y, c)));
            }
        }
    }
    return s;
}

Imagen gaussiano_secuencial(const Imagen&) {
    throw std::runtime_error("gaussiano: sin implementar");
}

Imagen gaussiano_paralelo(const Imagen&) {
    throw std::runtime_error("gaussiano: sin implementar");
}

Imagen sobel_secuencial(const Imagen& e) {
    if (e.canales != 1) throw std::runtime_error("sobel espera una imagen de un canal");
    Imagen s;
    s.ancho = e.ancho;
    s.alto = e.alto;
    s.canales = 1;
    s.datos.resize(static_cast<std::size_t>(e.ancho) * e.alto);
    for (int y = 0; y < e.alto; ++y) {
        const int arriba = recortar(y - 1, e.alto);
        const int abajo = recortar(y + 1, e.alto);
        for (int x = 0; x < e.ancho; ++x) {
            const int izq = recortar(x - 1, e.ancho);
            const int der = recortar(x + 1, e.ancho);
            // La vecindad de 3x3 se lee una sola vez y con ella se calculan
            // las dos máscaras:
            //   gx = [-1 0 1; -2 0 2; -1 0 1]    gy = [-1 -2 -1; 0 0 0; 1 2 1]
            const int a = e.en(izq, arriba, 0), b = e.en(x, arriba, 0), c = e.en(der, arriba, 0);
            const int d = e.en(izq, y, 0), f = e.en(der, y, 0);
            const int g = e.en(izq, abajo, 0), h = e.en(x, abajo, 0), i = e.en(der, abajo, 0);
            const int gx = (c + 2 * f + i) - (a + 2 * d + g);
            const int gy = (g + 2 * h + i) - (a + 2 * b + c);
            // redondear satura en 255, que es el min(255, ...) del enunciado.
            const double magnitud = std::sqrt(static_cast<double>(gx * gx + gy * gy));
            s.poner(x, y, 0, redondear(magnitud));
        }
    }
    return s;
}

Imagen sobel_paralelo(const Imagen&) {
    throw std::runtime_error("sobel: sin implementar");
}

Imagen otsu_secuencial(const Imagen&) {
    throw std::runtime_error("otsu: sin implementar");
}

Imagen otsu_paralelo(const Imagen&) {
    throw std::runtime_error("otsu: sin implementar");
}
