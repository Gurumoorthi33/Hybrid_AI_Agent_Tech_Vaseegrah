# rag_agent

## Local setup (Python-only)

1. Create and activate a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. Prepare app data:
   ```bash
   python setup.py
   ```

4. Run the FastAPI server:
   ```bash
   python server.py
   ```

5. Open the app:
   - `http://localhost:8000`

## Run with Python files directly

- Start the workflow CLI if needed:
  ```bash
  python main.py
  ```

- If you need to reingest files later:
  ```bash
  python ingest_files.py
  python ingest_mongo.py
  ```

## Notes

- The repository no longer uses Docker for local setup.
- The application runs directly on Python 3.11 with the installed dependencies.
- Data directories are created by `python setup.py`.

## Clean up Docker images and containers

If you previously built or ran Docker containers and want to remove them, use:

```bash
docker ps -a
docker rm <container_id_or_name>
docker images
docker rmi <image_id_or_name>
```

If you want to remove all stopped containers and unused images:

```bash
docker container prune
docker image prune -a
```
