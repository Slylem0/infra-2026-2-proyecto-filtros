## Qué cambia

<!-- Una o dos frases. -->

Closes #

## Cómo se probó

```console
$ make -C motor pruebas
```

## Checklist

- [ ] El motor compila con `-Wall -Wextra` sin avisos
- [ ] `make -C motor pruebas` pasa con `OMP_NUM_THREADS=1` y `8`
- [ ] No hay credenciales, llaves ni tokens en el diff
- [ ] No se suben binarios ni imágenes generadas
- [ ] Si cambia una decisión del enunciado, quedó justificada en `docs/`
- [ ] Moví la tarjeta a **👀 En revisión** y pedí revisión a otro integrante
