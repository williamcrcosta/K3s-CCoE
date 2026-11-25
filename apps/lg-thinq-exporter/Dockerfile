FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY exporter.py .
USER 10001:10001
EXPOSE 9810
CMD ["python", "-u", "exporter.py"]
