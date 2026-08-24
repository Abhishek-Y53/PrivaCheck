# Scaling Strategy

## 1. Initial Deployment

All components may be run locally using Docker Compose.

Example:

Frontend
API
PostgreSQL
Valkey
Crawler Worker
NLP Worker

## 2. Horizontal Scaling

The crawler should be independently scalable.

Example:

1 crawler worker
→ 5 crawler workers
→ 20 crawler workers

No change should be required to the frontend or API.

## 3. Resource Characteristics

Crawler:

High CPU/RAM usage
Browser-heavy

NLP:

CPU-heavy, potentially GPU-capable in future

API:

Low CPU/RAM relative to crawler

Database:

Persistent storage

Queue:

Task coordination

## 4. Future Production Architecture

Load Balancer
→ API instances

Queue
→ Crawler Worker Pool
→ NLP Worker Pool
→ Report Worker Pool

PostgreSQL
→ persistent data

Object Storage
→ large artifacts

## 5. Stateless Components

The following should ideally remain stateless:

- API
- Orchestrator
- Crawler worker
- NLP worker
- Report worker

State should be stored in:

- PostgreSQL
- Queue
- Artifact storage

## 6. Avoid Premature Complexity

Do not introduce Kubernetes, service meshes, or complex orchestration infrastructure during the initial project.

Docker Compose is sufficient for development.

The system should first prove the core functionality before adopting additional infrastructure.