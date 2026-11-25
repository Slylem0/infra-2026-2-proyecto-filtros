# Despliegue continuo a GKE

El workflow `.github/workflows/desplegar.yml` es el que despliega a la nube.
Corre en cada push a `main` y a mano (`workflow_dispatch`, con un `replicas`
opcional para el trabajador). Aplicar los manifiestos desde la terminal no
cuenta como despliegue automatizado.

Hay un solo despliegue a la vez (`concurrency: desplegar`) y el que está en
curso no se cancela: cortar un rollout a la mitad deja réplicas de dos
versiones.

## Jobs

| Job | Qué hace | Cuándo se salta |
|---|---|---|
| `probar` | Compila el motor con `-Wall -Wextra -Werror` y corre `make -C motor pruebas` con 1 y con 8 hilos (incluye la comparación byte a byte secuencial contra paralelo). | Nunca. Si falla, no se publica nada. |
| `publicar` | Se autentica por Workload Identity Federation, construye `trabajador` y `despachador` (contexto en la raíz del repositorio, `-f <componente>/Dockerfile`) y los publica en Artifact Registry como `${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${AR_REPO}/<componente>:<sha>`. Nunca `latest`. | Si falta `trabajador/Dockerfile` o `despachador/Dockerfile`: deja un aviso y termina en verde. |
| `desplegar` | Comprueba que el clúster exista, obtiene sus credenciales, fija las dos imágenes con `kustomize edit set image`, borra el Job `despachador` anterior (su plantilla es inmutable), hace `kubectl apply -k deploy/nube/` y espera `rollout status deployment/trabajador` (300 s). Escribe en el resumen de la corrida las imágenes desplegadas y `kubectl get pods -o wide`. | Si `publicar` se saltó, o si el clúster no existe (solo se enciende para medir): deja un aviso con las imágenes publicadas y termina en verde. |

Cada despliegue con clúster encendido vuelve a crear el Job `despachador`, es
decir, vuelve a lanzar el lote.

La evidencia para el informe es el resumen de la corrida de Actions que
desplegó: imagen con su SHA, registro del rollout y los pods con su nodo.

## Por qué Workload Identity Federation y no una llave JSON

- **Credenciales de vida corta.** GitHub emite un token OIDC por corrida;
  `google-github-actions/auth` lo cambia por un token de Google que expira en
  una hora. No existe una llave de larga vida.
- **Restringidas al repositorio.** El proveedor solo acepta tokens cuyo
  `repository` sea `Slylem0/infra-2026-2-proyecto-filtros`. Un fork o
  cualquier otro repositorio no puede suplantar a la cuenta de servicio.
- **Nada que rotar ni que filtrar.** Los dos secretos son identificadores, no
  credenciales: sin un token de este repositorio no sirven para nada. Una
  llave JSON, en cambio, da acceso completo a quien la lea y hay que rotarla.

## Configuración del repositorio

**Secretos** (Settings → Secrets and variables → Actions → Secrets), con los
valores que imprime `wif.sh`:

| Secreto | Forma |
|---|---|
| `WIF_PROVIDER` | `projects/<NUM>/locations/global/workloadIdentityPools/github/providers/github` |
| `GCP_SA` | `github-deployer@<PROJECT_ID>.iam.gserviceaccount.com` |

**Variables** (pestaña Variables). Solo `GCP_PROJECT_ID` es obligatoria; las
demás tienen el valor por defecto indicado.

| Variable | Por defecto |
|---|---|
| `GCP_PROJECT_ID` | (obligatoria) |
| `GCP_REGION` | `us-central1` |
| `GCP_ZONE` | `us-central1-a` |
| `GKE_CLUSTER` | `filtros` |
| `AR_REPO` | `filtros` |

Si hay Dockerfiles pero falta un secreto o `GCP_PROJECT_ID`, `publicar` falla
con un error que dice cuál falta.
