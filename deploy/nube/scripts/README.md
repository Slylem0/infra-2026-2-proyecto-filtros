# Google Cloud desde la CLI

Ejecuta los scripts desde `deploy/nube/scripts/` con Bash y una sesión de
`gcloud` con permisos para administrar las APIs, Artifact Registry, IAM y GKE.
El proyecto debe tener una cuenta de facturación vinculada. Para configurar
GitHub necesitas `gh` con acceso de escritura a los secretos y variables del
repositorio. Para obtener las credenciales locales de GKE instala también
`gke-gcloud-auth-plugin`.

Define `GCP_PROJECT_ID` con el ID de tu proyecto. Los demás valores se pueden
sobrescribir como variables de entorno.

| Variable | Valor predeterminado |
| --- | --- |
| `GCP_PROJECT_ID` | Obligatoria |
| `GCP_REGION` | `us-central1` |
| `GCP_ZONE` | `us-central1-a` |
| `GKE_CLUSTER` | `filtros` |
| `AR_REPO` | `filtros` |
| `GITHUB_REPO` | `Slylem0/infra-2026-2-proyecto-filtros` |
| `PRESUPUESTO_USD` | `150` |
| `BILLING_ACCOUNT` | Opcional. Requerida para crear el presupuesto. |

## Orden de uso

1. Ejecuta `./bootstrap.sh`. Habilita las APIs y prepara el repositorio Docker.
   Si defines `BILLING_ACCOUNT` con una cuenta en USD, crea un presupuesto del
   proyecto con alertas de gasto al 25, 50, 75 y 90 %. El gasto se acumula
   desde el día de creación del presupuesto antes de descontar créditos. Las
   alertas son avisos y los recursos siguen activos hasta apagarlos.
2. Ejecuta `./wif.sh`. Configura el pool y proveedor OIDC `github`, restringe
   la federación al repositorio autorizado y concede a `github-deployer`
   escritura en Artifact Registry y acceso de desarrollador a GKE. GitHub
   Actions usa credenciales temporales.
3. Ejecuta los comandos `gh secret set` y `gh variable set` impresos por
   `wif.sh`. Los secretos son `WIF_PROVIDER` y `GCP_SA`. Las variables se
   leen mediante `vars.*` en GitHub Actions.
4. Ejecuta `./cluster.sh up`. Revisa la estimación y confirma con `s`.
   El pool de tres nodos `e2-standard-4` deja espacio para las tres réplicas
   del trabajador y el despachador. El script obtiene las credenciales del
   clúster al terminar. La cuenta de servicio de los nodos debe tener acceso
   de lectura al repositorio Docker para descargar imágenes privadas.
5. Publica `trabajador:<sha>` y `despachador:<sha>` en
   `${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${AR_REPO}`, despliega con
   los manifiestos de `deploy/nube/` y mide. Ejecuta `./cluster.sh status`
   para ver los clústeres del proyecto y los nodos y discos del clúster elegido.
6. Ejecuta `./cluster.sh down` al terminar. Confirma con `s`. Primero
   elimina el clúster y luego busca y elimina los discos sin adjuntos con las
   etiquetas GKE correspondientes al nombre y la zona del clúster. La
   última lista de clústeres permite comprobar el apagado.

`up` y `down` aceptan `--yes` para confirmar de antemano. Conserva los
mismos valores de proyecto, clúster y zona durante la medición y el apagado.

Tarifas de referencia de Google Cloud para
[VM E2](https://cloud.google.com/products/compute/pricing/general-purpose),
[discos](https://cloud.google.com/products/block-storage),
[IPv4 externas](https://cloud.google.com/vpc/pricing#ipaddress) y
[gestión de GKE](https://cloud.google.com/kubernetes-engine/pricing).
