release: SKIP_STARTUP_DB=1 python -m flask --app run:app preparar-esquema
web: gunicorn run:app --workers 2 --threads 4 --timeout 60 --bind 0.0.0.0:$PORT
