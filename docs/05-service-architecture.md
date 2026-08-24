# Service Architecture

## 1. Initial Services

The initial system should have the following logical services:

1. API Service
2. Scan Orchestrator
3. Crawler Worker
4. Compliance/Analysis Worker
5. NLP Worker
6. Report Generator

These should initially be implemented as modular components within the same repository.

They do not all need to be deployed independently during the first development phase.

## 2. Future Microservice Decomposition

If system scale increases, the following can become independent deployable services:

api-service
crawler-service
analysis-service
nlp-service
report-service

The API should communicate with workers through asynchronous jobs rather than direct synchronous calls.

## 3. Why Not Create Many Microservices Immediately?

A large number of independently deployed services introduces:

- Deployment complexity
- Networking complexity
- Debugging complexity
- Monitoring requirements
- Configuration overhead
- More infrastructure

For a student project, modular boundaries provide most of the architectural benefit without unnecessary operational overhead.

## 4. Independent Scaling

Crawler workers are expected to be the most resource-intensive component.

Therefore crawler workers should be horizontally scalable.

Example:

crawler-1
crawler-2
crawler-3
...
crawler-N

The same principle applies to NLP workers if policy analysis becomes resource intensive.

## 5. Service Communication

API → Queue → Worker

Worker → Database

Worker → Queue → Next Worker

Frontend → API

The browser worker should not directly communicate with the frontend.