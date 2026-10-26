FROM python:3.12.14-slim-bookworm
WORKDIR /app
COPY service/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir -r /tmp/requirements.lock && useradd --uid 10001 --create-home app
COPY recommendations ./recommendations
COPY pipeline/publication.py pipeline/facts.py ./pipeline/
COPY insight_generation ./insight_generation
COPY service ./service
RUN mkdir -p /state /catalog /data/reports && chown -R app:app /state
USER app
ENV ALFA_CATALOG=/catalog/catalog.sqlite ALFA_ASSETS=/catalog/service-assets.sqlite ALFA_SERVICE_STATE=/state/service.sqlite ALFA_FEEDBACK=/state/feedback.sqlite ALFA_DATA_DIR=/data
HEALTHCHECK --interval=20s --timeout=5s --start-period=30s CMD python -c "import urllib.request,os; r=urllib.request.Request('http://127.0.0.1:8091/health',headers={'X-Alfa-Internal':os.getenv('ALFA_INTERNAL_TOKEN','')}); urllib.request.urlopen(r,timeout=4)"
CMD ["python","-m","service.launch"]
