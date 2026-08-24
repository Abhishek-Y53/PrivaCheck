# API Design

## 1. API Technology

FastAPI

Base path:

/api/v1

## 2. Scan APIs

### Create Scan

POST /api/v1/scans

Request:

{
    "url": "https://example.com"
}

Response:

{
    "scan_id": 123,
    "status": "QUEUED"
}

### Get Scan

GET /api/v1/scans/{scan_id}

### Get Results

GET /api/v1/scans/{scan_id}/results

### Get Checks

GET /api/v1/scans/{scan_id}/checks

### Get Report

GET /api/v1/scans/{scan_id}/report

## 3. Future APIs

POST /api/v1/scans/{scan_id}/rescan

DELETE /api/v1/scans/{scan_id}

GET /api/v1/scans

## 4. API Principle

The API handles requests and orchestration.

It does not execute browser crawling synchronously.

## 5. API Documentation

FastAPI's OpenAPI support should provide interactive development documentation.