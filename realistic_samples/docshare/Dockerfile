FROM python:3.11

WORKDIR /app

# Install system dependencies needed by the conversion pipeline.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      pandoc \
      rsync \
      curl \
      ca-certificates \
      && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

EXPOSE 8080

# Run as root so the conversion subprocess can write to the shared volume
# mounted from the worker tier. See infra/README.md.
CMD ["python", "-m", "docshare.app"]
