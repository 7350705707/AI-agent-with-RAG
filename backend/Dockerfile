FROM python:3.12
WORKDIR /app

# Install build tools (needed if any packages compile from source)
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create venv inside container
# RUN python -m venv /opt/venv
# ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements and install from PyPI
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copy backend code
COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
