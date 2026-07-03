# SFMShop

## Настройка окружения

### 1. Создание виртуального окружения

Windows:

```cmd
python -m venv venv
venv\Scripts\activate.bat
```

Linux/macOS:

```bash
python -m venv venv
source venv/bin/activate
```

### 2. Обновление pip

```bash
python -m pip install --upgrade pip
```

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

`requirements.txt` должен содержать зафиксированные версии всех зависимостей проекта, включая FastAPI, pytest, SQLAlchemy, Alembic, Redis, MongoDB/Motor/PyMongo, RabbitMQ-клиенты, PostgreSQL-драйверы и прочие библиотеки.

**Для обновления окружения используем команду:**
```bash
pip freeze > requirements.txt
```