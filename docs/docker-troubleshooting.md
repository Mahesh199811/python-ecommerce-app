# Docker and Compose troubleshooting

Use this when an image build fails or a container will not stay up. Run the commands from the repository root unless a step says otherwise.

The four images are built from Dockerfiles under `docker/`. The build context is the repository root, because each Dockerfile copies `requirements.txt` and application code from that root. Compose is defined in `compose.yaml`.

| Service | Image | Published port | Health URL |
| --- | --- | --- | --- |
| user-service | `ecommerce-user-service:1.0` | 5001 | http://127.0.0.1:5001/health |
| product-service | `ecommerce-product-service:1.0` | 5002 | http://127.0.0.1:5002/health |
| order-service | `ecommerce-order-service:1.0` | 5003 | http://127.0.0.1:5003/health |
| frontend | `ecommerce-frontend:1.0` | 5004 | http://127.0.0.1:5004/health |

The storefront also exposes http://127.0.0.1:5004/api/health, which checks the other three services.

## First checks

```bash
docker compose ps
docker compose logs --tail 80
docker ps -a
curl -sS http://127.0.0.1:5004/api/health
```

`docker compose config` prints the resolved Compose file and fails if the YAML is invalid.

## Build failures

Build one image the same way Compose does:

```bash
docker build -f docker/user-service/Dockerfile -t ecommerce-user-service:1.0 .
```

The trailing `.` is the build context. It must be the repository root.

### `COPY` cannot find a file

Symptom:

```text
failed to compute cache key: "/services/user_service": not found
COPY requirements.txt .
```

Cause: the command was run inside `docker/user-service`, so Docker only received that directory. `requirements.txt` and `services/user_service/` are not there.

Fix: change to the repository root and pass `-f`:

```bash
cd /path/to/python-ecommerce-app
docker build -f docker/user-service/Dockerfile -t ecommerce-user-service:1.0 .
```

The same rule applies to the product, order, and frontend Dockerfiles.

### A needed file is missing from the context

`.dockerignore` drops git metadata, virtualenvs, caches, `.env` files, and logs. It keeps `.env.example`. If a `COPY` fails and the file exists on disk, check whether `.dockerignore` excluded it.

```bash
docker build -f docker/user-service/Dockerfile -t ecommerce-user-service:1.0 . --progress=plain
```

### Base image cannot be pulled

Symptom: `failed to resolve` or a timeout talking to `registry-1.docker.io`.

Check that Docker Desktop is running, then retry the pull:

```bash
docker pull python:3.12-slim
```

### Pip install fails inside the image

The install step is `pip install --no-cache-dir -r requirements.txt`. A failure here is usually a network problem during the build or a bad pin in `requirements.txt`. Rebuild that one service after the dependency file is fixed:

```bash
docker compose build --no-cache user-service
```

`--no-cache` forces the `RUN pip install` layer to run again. Use it when the requirements changed but Docker keeps an old cached layer.

### Image is in use and will not delete

Symptom: `image is being used by a stopped container` or the `U` marker in `docker images`.

Stop and remove the containers that reference it, then delete the image:

```bash
docker ps -a
docker rm -f <container>
docker rmi ecommerce-user-service:1.0
```

## Container failures

### Port is already allocated

Symptom:

```text
Bind for 0.0.0.0:5001 failed: port is already allocated
```

Another container, or a local `./scripts/run_local.sh` process, already owns 5001, 5002, 5003, or 5004.

```bash
docker ps --format 'table {{.Names}}\t{{.Ports}}\t{{.Status}}'
lsof -nP -iTCP:5001 -sTCP:LISTEN
```

Stop the old containers before `docker compose up`:

```bash
docker rm -f user-service product-service order-service frontend
docker compose up --build
```

### Container exits immediately

```bash
docker compose ps -a
docker compose logs user-service
docker inspect user-service --format '{{.State.Status}} {{.State.ExitCode}} {{.State.Error}}'
```

Read the last log lines before the exit. A non-zero exit from uvicorn usually means the app crashed on import or could not bind its port inside the container.

### Health check stays unhealthy

Each image checks its own `/health` endpoint. Compose waits for `service_healthy` before starting the order service and the frontend.

```bash
docker inspect user-service --format '{{json .State.Health}}'
docker compose logs user-service
```

`health: starting` during the first 10 seconds is normal. That is the `start_period`. After that, three failed checks mark the container unhealthy and block anything that depends on it.

Test the endpoint from the host:

```bash
curl -sv http://127.0.0.1:5001/health
```

### Order service or frontend cannot reach another service

Inside Compose, service names are DNS names: `user-service`, `product-service`, and `order-service`. The order service calls `http://user-service:5001` and `http://product-service:5002`. The frontend calls all three.

`127.0.0.1` inside a container is that container, not the host and not a sibling container.

Confirm the URLs the process actually received:

```bash
docker compose exec order-service printenv USER_SERVICE_URL PRODUCT_SERVICE_URL
docker compose exec frontend printenv USER_SERVICE_URL PRODUCT_SERVICE_URL ORDER_SERVICE_URL
```

Then call a dependency from inside the order container:

```bash
docker compose exec order-service python -c "import urllib.request; print(urllib.request.urlopen('http://user-service:5001/health', timeout=3).read())"
```

If that fails, both containers must be on the Compose network. `docker compose ps` and `docker network inspect` show membership. Do not mix a manually started container on the old `stride` network with a Compose stack unless both are attached to the same network and the DNS names match.

### Database file cannot be created

The API containers run as user `10001` and write SQLite under `/app/data`. Compose mounts named volumes there (`user-data`, `product-data`, `order-data`).

Symptom in the logs: `unable to open database file` or `Permission denied`.

```bash
docker compose exec user-service ls -ld /app/data
docker compose exec user-service id
```

`id` should show uid `10001`. The data directory must be writable by that user. A bind mount of a root-owned host folder will fail. Named volumes created by this Compose file are the supported path.

Reset a volume only when the data can be discarded:

```bash
docker compose down
docker volume rm python-ecommerce-app_user-data
docker compose up
```

The volume name is prefixed with the Compose project name. `docker volume ls` shows the exact name.

### Frontend is up but the shop shows no data

The frontend `/health` endpoint only proves the storefront process is running. The aggregate check is the one that matters:

```bash
curl -sS http://127.0.0.1:5004/api/health
```

A `503` with `"users": false` or the same for products or orders means that upstream container is down or unreachable. Check that service's logs next.

## Compose commands

| Goal | Command |
| --- | --- |
| Validate the file | `docker compose config` |
| Build and start | `docker compose up --build` |
| Start in the background | `docker compose up --build -d` |
| Status | `docker compose ps` |
| Follow logs | `docker compose logs -f` |
| Logs for one service | `docker compose logs -f order-service` |
| Restart one service | `docker compose restart order-service` |
| Rebuild one service | `docker compose up -d --build order-service` |
| Stop, keep volumes | `docker compose stop` |
| Stop and remove containers | `docker compose down` |
| Remove containers and volumes | `docker compose down -v` |

`docker compose down` removes the Compose containers and network. It leaves named volumes in place, so SQLite data survives the next `up`. `down -v` deletes that data.

## Manual container commands

These apply when a container was started with `docker run` instead of Compose.

```bash
docker ps -a
docker logs --tail 100 user-service
docker inspect user-service
docker start user-service
docker stop user-service
docker rm user-service
```

Remove only stopped containers:

```bash
docker ps -aq -f status=exited
docker container prune
```

`docker container prune` asks for confirmation unless `-f` is passed. It does not remove running containers.

## What to collect before changing anything

When a failure is not obvious, save this output:

```bash
docker compose ps -a
docker compose logs --tail 100
docker compose config
curl -sS -i http://127.0.0.1:5001/health
curl -sS -i http://127.0.0.1:5002/health
curl -sS -i http://127.0.0.1:5003/health
curl -sS -i http://127.0.0.1:5004/api/health
```
