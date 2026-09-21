FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY invoice_api.py .

EXPOSE 5080

CMD ["gunicorn", "--bind", "0.0.0.0:5080", "invoice_api:app"]
