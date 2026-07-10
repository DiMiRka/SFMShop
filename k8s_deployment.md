# Развертывание SFMShop в Kubernetes

## Состав конфигурации

- `deployment.yaml` создает `Deployment` приложения SFMShop с 3 репликами
- `service.yaml` создает `Service` типа `LoadBalancer` для доступа к приложению на порту `8000`

`Service` находит pods по label `app: sfmshop`. Этот label указан и в selector Deployment, и в template подов

## Secret с переменными окружения

Приложение читает настройки из env переменных\
В `deployment.yaml` переменные для БД, Redis и других внешних сервисов подключены через `secretKeyRef`

Создать Secret из `.env` можно так:

```powershell
kubectl create secret generic sfmshop-secrets --from-env-file=.env
```

Или создать Secret вручную через `--from-literal`:

```powershell
kubectl create secret generic sfmshop-secrets `
  --from-literal=DB_HOST=postgres `
  --from-literal=DB_PORT=5432 `
  --from-literal=DB_NAME=sfmshop `
  --from-literal=DB_USER=postgres `
  --from-literal=DB_PASSWORD=change-me `
  --from-literal=DB_REPLICA_HOST=postgres `
  --from-literal=DB_REPLICA_PORT=5432 `
  --from-literal=DB_REPLICA_NAME=sfmshop `
  --from-literal=DB_REPLICA_USER=postgres `
  --from-literal=DB_REPLICA_PASSWORD=change-me `
  --from-literal=REDIS_HOST=redis `
  --from-literal=REDIS_PORT=6379 `
  --from-literal=REDIS_DB=0 `
  --from-literal=MONGO_URL=mongodb://mongo:27017 `
  --from-literal=RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/ `
  --from-literal=JWT_SECRET=change-me `
  --from-literal=CORS_ORIGINS='["http://localhost:3000"]' `
  --from-literal=RATE_LIMIT_LOGIN=5/minute
```

Перед созданием Secret нужно убедиться, что выбран Kubernetes context:

```powershell
kubectl config current-context
kubectl get nodes
```

## Деплой

Сначала нужно собрать Docker образ приложения:

```powershell
docker build -t sfmshop:latest .
```

Затем применить манифесты:

```powershell
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
```

Проверить ресурсы:

```powershell
kubectl get deployments
kubectl get pods
kubectl get services
```