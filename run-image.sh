#!/bin/bash

# Set variables
IMAGE_NAME="media-identifier-api"
TAG="latest"
CONTAINER_NAME="media-identifier-api"
PORT=10147

# Check if container already exists
if [ "$(docker ps -a -q -f name=${CONTAINER_NAME})" ]; then
    echo "Container ${CONTAINER_NAME} already exists. Stopping and removing..."
    docker stop ${CONTAINER_NAME} >/dev/null 2>&1
    docker rm ${CONTAINER_NAME} >/dev/null 2>&1
fi

# Print information
echo "Starting container: ${CONTAINER_NAME}"
echo "Using image: ${IMAGE_NAME}:${TAG}"
echo "Exposing port: ${PORT}"
echo "----------------------------------------------"

# Run the container
docker run -d \
    --name ${CONTAINER_NAME} \
    -p ${PORT}:${PORT} \
    --restart unless-stopped \
    ${IMAGE_NAME}:${TAG}

# Check if container started successfully
if [ $? -eq 0 ]; then
    echo "----------------------------------------------"
    echo "✅ Container started successfully: ${CONTAINER_NAME}"
    echo "API is available at: http://localhost:${PORT}/api/guess"
    echo "Health check at: http://localhost:${PORT}/api/health"
    
    # Wait a moment for the container to initialize
    echo "Waiting for container to initialize..."
    sleep 3
    
    # Check container status
    CONTAINER_STATUS=$(docker inspect --format='{{.State.Status}}' ${CONTAINER_NAME})
    echo "Container status: ${CONTAINER_STATUS}"
    
    # Optional: Check health status if available
    if docker inspect --format='{{.State.Health.Status}}' ${CONTAINER_NAME} >/dev/null 2>&1; then
        HEALTH_STATUS=$(docker inspect --format='{{.State.Health.Status}}' ${CONTAINER_NAME})
        echo "Health status: ${HEALTH_STATUS}"
    fi
else
    echo "----------------------------------------------"
    echo "❌ Failed to start container"
    exit 1
fi