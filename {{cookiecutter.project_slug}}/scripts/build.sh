#!/bin/bash

# Exit in case of error
set -e

# Build and run containers
docker-compose up -d

# Hack to wait for postgres container to be up before running database migrations
sleep 5;

# Run migrations
docker-compose run --rm backend python manage.py migrate

# Create initial data
docker-compose run --rm backend python3 app/initial_data.py