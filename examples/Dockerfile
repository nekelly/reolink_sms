FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy the parent directory (reolink_aio package) into the container
COPY .. /app

# Install Python dependencies (includes Twilio for SMS)
RUN pip install --no-cache-dir -r requirements.txt && \
    pip list | grep -i twilio

# Create recordings directory
RUN mkdir -p /app/examples/recordings

# Set the working directory to examples
WORKDIR /app/examples

# Run the motion event retrieval script
CMD ["python", "retrieve_motion_events.py"]
