# Manifiestos de Kubernetes (`deploy/nube/`)

Despliegue del servicio de filtros en un clúster administrado. Los manifiestos
son portables: no nombran `storageClass`, anotaciones ni registros de un
proveedor concreto (GKE o EKS).

| Archivo | Qué es |
|---|---|
| `namespace.yaml` | Namespace `filtros` |
| `configmap.yaml` | `OMP_NUM_THREADS=2`, `FILTROS`, `CONCURRENCIA=8` |
| `trabajador-deployment.yaml` | 3 réplicas del trabajador, sondas, recursos, sin root |
| `trabajador-service.yaml` | Service ClusterIP `trabajador:8000` |
| `datos-pvc.yaml` | PVC RWO de 1 GiB con `entrada/` y `salida/` |
| `despachador-job.yaml` | Job que corre el lote contra `http://trabajador:8000` y termina |
| `kustomization.yaml` | Lista lo anterior y sustituye las imágenes |

## Cómo aplicar

Se aplica **con Kustomize** (`-k`), no con `-f`: `kubectl apply -f deploy/nube/`
intenta crear `kustomization.yaml` como un objeto y falla, y además no sustituye
las imágenes.

```console
# 1. Apuntar las imágenes a la etiqueta inmutable (nunca latest).
#    Requiere el binario kustomize; kubectl no trae "kustomize edit".
$ cd deploy/nube
$ kustomize edit set image \
    trabajador=<REGISTRO>/trabajador:<SHA> \
    despachador=<REGISTRO>/despachador:<SHA>
$ cd -

# 2. Revisar y aplicar.
$ kubectl kustomize deploy/nube/            # YAML final
$ kubectl apply -k deploy/nube/
$ kubectl -n filtros rollout status deployment/trabajador --timeout=300s

# 3. Seguir el lote y leer el throughput.
$ kubectl -n filtros wait --for=condition=complete job/despachador --timeout=30m
$ kubectl -n filtros logs job/despachador
```

Para medir con 1 réplica: `kubectl -n filtros scale deployment/trabajador --replicas=1`,
esperar el rollout y volver a lanzar el Job (ver abajo).

**Volver a correr el Job.** La plantilla de un Job es inmutable. El Job se
borra solo una hora después de terminar (`ttlSecondsAfterFinished: 3600`);
para relanzarlo antes: `kubectl -n filtros delete job despachador` y
`kubectl apply -k deploy/nube/`. Si el CI aplica con una imagen nueva del
despachador mientras el Job anterior aún existe, el `apply` falla por esa
inmutabilidad.

**Datos de entrada.** El PVC nace vacío. Alguien tiene que dejar el lote en
`/datos/entrada` antes de que el despachador lo lea (que el propio despachador
lo genere, o un paso de copia). Eso queda para el issue del despachador.

**Clase de almacenamiento.** El PVC usa la clase por defecto del clúster. GKE
trae una (`standard-rwo`). En EKS recientes no hay clase por defecto: hay que
instalar el driver EBS CSI y marcar una clase como default, o el PVC se queda
en `Pending`. Algunos discos tienen tamaño mínimo y el proveedor redondea hacia
arriba los 1 GiB pedidos; no cambia nada para el lote.

## Justificación de `requests` y `limits`

| Contenedor | CPU request | CPU limit | Memoria request | Memoria limit | QoS |
|---|---|---|---|---|---|
| trabajador | 2 | 2 | 512Mi | 512Mi | Guaranteed |
| despachador | 500m | 1 | 256Mi | 256Mi | Burstable |

### CPU del trabajador: 2 = `OMP_NUM_THREADS`

El motor abre `OMP_NUM_THREADS=2` hilos y los dos calculan sin bloquearse.
El limit de CPU se aplica con la cuota de CFS: en cada periodo de 100 ms el
contenedor puede gastar `limit × 100 ms` de CPU entre todos sus hilos.

- **Limit menor que los hilos** (p. ej. `1` con 2 hilos): los dos hilos gastan
  la cuota de 100 ms en ~50 ms de reloj y el contenedor queda congelado
  (*throttled*) el resto del periodo. La imagen tarda lo mismo o más que con un
  hilo, y en el informe parecería que OpenMP no escala cuando lo que pasa es
  que la cuota lo frena. El congelamiento es de todo el cgroup hasta el
  siguiente periodo, así que el tiempo crece en escalones de ~50 ms por
  periodo en vez de forma continua.
- **Limit igual a los hilos** (`2`): los dos hilos corren a la vez sin agotar
  la cuota. La capa Python casi no consume mientras el motor trabaja.
- **Request igual al limit**: el scheduler reserva 2 núcleos completos por
  réplica, de modo que se sabe cuánta máquina tenía cada una (es lo que pide
  el enunciado para poder interpretar la medición) y las réplicas no se roban
  CPU si caen en el mismo nodo. Con requests = limits en CPU y memoria el pod
  es **Guaranteed**, el último en ser desalojado.

Si se cambia `OMP_NUM_THREADS`, se cambia la CPU en la misma proporción.

**Consecuencia para el clúster.** 3 réplicas × 2 CPU = 6 CPU reservadas, más
el despachador (0,5) y los pods del sistema. Un nodo de 4 vCPU deja algo menos
de 4 asignables, así que solo cabe un trabajador por nodo: hacen falta 3 nodos
de 4 vCPU, o 2 de 8 vCPU. Por eso el rollout usa `maxSurge: 0` y
`maxUnavailable: 1`: sustituye las réplicas de a una sin pedir un cuarto hueco
de 2 CPU que el clúster podría no tener.

### Memoria del trabajador: 512Mi

Una imagen de 1024×1024 en el motor (un byte por componente):

| Buffer | Tamaño |
|---|---|
| Cuerpo de la petición (PPM RGB) en Python | 3 MiB |
| Archivo temporal de entrada en `/tmp` | 3 MiB |
| `Imagen` de entrada en el motor | 3 MiB |
| Salida de `gris` (1 canal) | 1 MiB |
| Gaussiano: intermedio + salida | 2 MiB (8 MiB si el intermedio es `double`) |
| `sobel`, `otsu` | 1 MiB cada uno |
| Salida PGM leída de vuelta + respuesta | 2 MiB |

Unos 15–25 MiB por imagen en vuelo. Con `CONCURRENCIA=8` repartida entre 3
réplicas, cada una tiene ~3 peticiones a la vez (8 en el peor caso, con una
sola réplica): ≤ 200 MiB. Sumando el intérprete y el servidor HTTP
(~60–100 MiB), 512Mi deja margen sin reservar memoria ociosa. Request = limit
porque la memoria no se puede quitar como la CPU: pasar el limit es un
OOMKill, no un frenado.

### Despachador: 500m–1 CPU, 256Mi

El despachador espera la red casi todo el tiempo: lee un PPM, lo envía y
escribe el PGM. 500m reservados bastan; el limit de 1 CPU le deja ráfagas para
la lectura/escritura sin competir con los trabajadores. En memoria, 8 peticiones
en vuelo × (3 MiB de entrada + 1 MiB de salida) = 32 MiB más el intérprete;
256Mi sobra.

### Almacenamiento: 1 GiB

64 PPM de 1024×1024 ≈ 64 × 3 MiB = 192 MiB de entrada y 64 PGM ≈ 64 MiB de
salida: ~256 MiB. 1 GiB da 4× de margen para corridas repetidas o un lote algo
mayor.

## Otras decisiones

- **Sondas.** `startupProbe` sobre `/healthz` da hasta 60 s para arrancar antes
  de que cuente la liveness. Liveness cada 10 s con 3 fallos: un trabajador
  ocupado con una imagen (~0,5 s) no se reinicia por error. Readiness sobre
  `/readyz` cada 5 s: si el binario del motor no responde, el Service deja de
  mandarle peticiones sin reiniciarlo.
- **Seguridad.** UID 10001 sin root, sin escalada de privilegios, sin
  capacidades, raíz de solo lectura con `/tmp` en un `emptyDir` y sin token de
  la API montado. El `fsGroup` del Job deja el PVC escribible por ese UID. Las
  imágenes deben funcionar con un UID arbitrario (o crear el 10001).
- **Reparto.** El Service balancea por **conexión**, no por petición. Si el
  despachador reusa una sola conexión keep-alive (p. ej. una única
  `requests.Session`), todas las imágenes van a la misma réplica. Con varias
  conexiones en paralelo (una por hilo) el reparto sí se ve.
- **Job.** `backoffLimit: 2` cubre que el Job arranque antes de que los
  trabajadores estén listos; `activeDeadlineSeconds: 1800` corta un lote colgado
  para no gastar crédito.
