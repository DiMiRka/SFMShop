FROM python:3.11-slim AS builder
WORKDIR /app
COPY ../requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


FROM python:3.11-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH=/root/.local/bin:$PATH

COPY --from=builder /root/.local /root/.local
COPY .. .

CMD ["uvicorn", "src.api.main:sfmshop_app", "--host", "0.0.0.0", "--port", "8000"]