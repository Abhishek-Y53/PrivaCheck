# Database Design

## 1. Database

PostgreSQL

## 2. Core Entities

Initial entities:

- User
- Scan
- ScanTarget
- Page
- NetworkRequest
- Cookie
- StorageSnapshot
- ConsentPass
- PolicyDocument
- ComplianceCheck
- CheckResult
- Evidence
- Report

## 3. High-Level Relationships

User
1 ── N
Scan

Scan
1 ── 1
ScanTarget

Scan
1 ── N
Page

Scan
1 ── N
NetworkRequest

Scan
1 ── N
Cookie

Scan
1 ── N
StorageSnapshot

Scan
1 ── N
ConsentPass

Scan
1 ── N
PolicyDocument

Scan
1 ── N
CheckResult

CheckResult
1 ── N
Evidence

Scan
1 ── 1
Report

## 4. Important Design Principle

Raw observations and interpreted compliance results should be separated.

Observation data:
"What happened?"

Compliance result:
"What does the system conclude about it?"

## 5. Future

The complete ER diagram and database models should be finalized before implementing large parts of the application.