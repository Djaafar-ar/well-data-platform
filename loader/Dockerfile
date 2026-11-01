FROM python:3.12-slim

# Run as a non-root user: a batch job does not need root to read files and write to the database
RUN useradd --create-home app
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY common.py production_rules.py las_rules.py load_production.py load_las.py load_all.py ./
USER app

ENTRYPOINT ["python"]
CMD ["load_all.py", "/fixtures", "/data"]
