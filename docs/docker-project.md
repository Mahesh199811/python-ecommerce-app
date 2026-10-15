# Docker Production App

## Objective

Containerize a Python FastAPI e-commerce application using Docker.

## Services

| Service | Port |
|---|---:|
| User Service | 5001 |
| Product Service | 5002 |
| Order Service | 5003 |
| Frontend / API Gateway | 5004 |

## Implementation

- Built separate Docker images for all four services.
- Ran each service in an independent container.
- Published container ports for local testing.
- Configured Docker health checks.
- Ran the User Service as a non-root user.
- Verified all service health endpoints.
- Verified the frontend aggregate health endpoint.
- Added a `.dockerignore` file.
- Practiced stopping and restarting a container.

## Verification

The following endpoint returned HTTP 200:

`http://localhost:5004/api/health`

The response reported the User, Product, and Order services as healthy.

## Key Learnings

- Dockerfiles and image layers
- Image tags and containers
- Port publishing
- Container health checks
- Non-root container execution
- Container logs and inspection
- Basic failure recovery

## Next Project

Docker Compose: define and run the multi-container application
using a declarative configuration.
