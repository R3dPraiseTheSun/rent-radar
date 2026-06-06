FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV APP_HOME=/app

WORKDIR ${APP_HOME}

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY README.md ./README.md

RUN mkdir -p /data/raw /data/exports /data/images /logs

ENV RENT_RADAR_DB_URL=sqlite:////data/rent_radar.sqlite
ENV RENT_RADAR_DATA_DIR=/data
ENV RENT_RADAR_LOG_DIR=/logs

EXPOSE 8501

CMD ["streamlit", "run", "app/ui/streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501"]