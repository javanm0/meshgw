# Use a smaller base image
FROM python:3.9-alpine AS builder

# Set the working directory in the container
WORKDIR /app

# Install required system packages
RUN apk add --no-cache \
    build-base \
    libffi-dev \
    openssl-dev \
    python3-dev \
    py3-pip \
    iputils

# Create a virtual environment
RUN python -m venv /opt/venv

# Activate the virtual environment and upgrade pip
RUN /opt/venv/bin/pip install --upgrade pip

# Copy the application code into the container
COPY . .

# Install dependencies in the virtual environment
RUN /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# Final stage: Use a minimal runtime image
FROM python:3.9-alpine

# Set the working directory in the container
WORKDIR /app

# Install the ping utility in the final stage
RUN apk add --no-cache iputils

# Copy the virtual environment from the builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy the application code into the container
COPY . .

# Set the environment variable for the virtual environment
ENV PATH="/opt/venv/bin:$PATH"

# Run the application when the container launches
CMD ["python", "meshgw-receiver.py"]