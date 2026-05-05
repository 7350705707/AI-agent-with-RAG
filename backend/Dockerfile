FROM python:3.12
WORKDIR /app


# Install build tools for compiling packages from source
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \   
    && rm -rf /var/lib/apt/lists/*

# Copy dependency packages for offline install
COPY packages/ /packages/
COPY requirements.txt .
RUN pip install --no-index --find-links=/packages -r requirements.txt

# Copy backend code
COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
