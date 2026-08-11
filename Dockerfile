FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=5000 \
    DATA_DIR=/data \
    SPACY_MODEL=es_core_news_lg \
    NLTK_DATA=/usr/local/share/nltk_data

WORKDIR /app

# Some scientific Python dependencies need a compiler when wheels are not
# available for the target architecture.  They are removed after installation
# so the runtime image remains small.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
# text2graphapi loads es_core_news_sm by name while building association graphs.
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && python -m spacy download es_core_news_sm \
    && python -m spacy download es_core_news_lg \
    && python -m nltk.downloader -d "$NLTK_DATA" punkt stopwords wordnet \
    && apt-get purge -y --auto-remove build-essential

COPY . ./

RUN useradd --create-home --uid 1000 diccionario \
    && mkdir -p /data \
    && chown -R diccionario:diccionario /app /data

USER diccionario

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "600", "app:app"]
