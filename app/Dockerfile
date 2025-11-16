FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy the entire project into /build
COPY .. /build

# Install Python dependencies from root
RUN pip install --no-cache-dir -r /build/requirements.txt

# Install the reolink_aio package
RUN pip install --no-cache-dir /build

# Copy app files to /app
COPY . /app/

# Create recordings directory
RUN mkdir -p /app/recordings

# Run the motion event retrieval script
CMD ["python", "retrieve_motion_events.py"]
