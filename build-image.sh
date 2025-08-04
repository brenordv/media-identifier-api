#!/bin/bash

# Set variables
IMAGE_NAME="media-identifier-api"
TAG="latest"

# Print information
echo "Building Docker image: ${IMAGE_NAME}:${TAG}"
echo "----------------------------------------------"

# Build the Docker image
docker build -t ${IMAGE_NAME}:${TAG} .

# Check if build was successful
if [ $? -eq 0 ]; then
    echo "----------------------------------------------"
    echo "✅ Build successful: ${IMAGE_NAME}:${TAG}"
    echo "Run the container with: ./run-image.sh"
else
    echo "----------------------------------------------"
    echo "❌ Build failed"
    exit 1
fi