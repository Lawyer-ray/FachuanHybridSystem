# Docker 部署入口

在 `backend/` 目录下执行：

```bash
docker compose -f deploy/docker/docker-compose.yml up --build
docker compose -f deploy/docker/docker-compose.yml -f deploy/docker/docker-compose.postgres.yml up --build
```

