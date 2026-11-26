FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY eden ./eden
RUN useradd --create-home --uid 10001 eden && mkdir -p /data && chown -R eden:eden /app /data
USER eden
ENV EDEN_DB=/data/eden.db
EXPOSE 8000
CMD ["uvicorn", "eden.main:app", "--host", "0.0.0.0", "--port", "8000"]
