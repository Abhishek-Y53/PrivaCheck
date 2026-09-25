# PrivaCheck

**PrivaCheck** is a configurable web compliance assessment platform that analyzes websites using browser-level observations, network activity, DOM information, storage behavior, and declarative compliance rules.

The system is designed around a clear separation between **data collection** and **compliance evaluation**:

> **The crawler collects evidence. The rule engine decides whether that evidence satisfies a rule.**

This architecture allows compliance frameworks and individual checks to be changed through configuration files rather than hard-coding framework-specific logic into the crawler.

---

## Overview

Modern websites can perform privacy- and security-relevant actions through mechanisms that are not always visible in the initial HTML source.

PrivaCheck therefore analyzes a website through a real browser and collects structured observations from multiple sources, including:

* DOM elements and visible text
* Cookies
* Local storage and session storage
* Network requests and responses
* Links
* Forms and input elements
* Buttons and consent controls
* Browser state before and after user interaction

These observations are then passed to a generic rule engine.

```text
                    ┌─────────────────────┐
                    │      Target URL      │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │       Crawler       │
                    │  Playwright Browser  │
                    └──────────┬──────────┘
                               │
                 ┌─────────────┴─────────────┐
                 │                           │
                 ▼                           ▼
        ┌─────────────────┐         ┌─────────────────┐
        │ Single-Pass     │         │ Two-Pass        │
        │ Collection      │         │ Collection      │
        └────────┬────────┘         └────────┬────────┘
                 │                           │
                 └─────────────┬─────────────┘
                               ▼
                    ┌─────────────────────┐
                    │    Observations     │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    Rule Engine      │
                    └──────────┬──────────┘
                               │
                         reads YAML
                               │
                               ▼
                    ┌─────────────────────┐
                    │    YAML Rules       │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   Check Results     │
                    │ Status + Evidence   │
                    └─────────────────────┘
```

---

## Key Goals

PrivaCheck is being developed with the following design goals:

### 1. Configurable compliance rules

Compliance rules are defined in YAML rather than embedded directly into Python code.

A rule can specify:

* What observation type it consumes
* Which evaluator should process it
* Conditions that must be satisfied
* Expected result
* Severity
* Recommendation
* Optional state-difference assertions

This makes the rule engine reusable across different compliance frameworks.

### 2. Evidence-driven assessment

A result should not simply say:

```text
FAIL
```

It should also explain **why** the rule failed and provide the observations that caused the evaluation.

The target result is therefore:

```text
Rule
  ↓
Evaluation
  ↓
Status
  ↓
Explanation
  ↓
Evidence
```

### 3. Separation of responsibilities

The architecture intentionally separates:

```text
Browser/Crawler
      ↓
Observation Collection
      ↓
Rule Evaluation
      ↓
Compliance Result
```

The crawler does not contain GDPR-specific decision logic.

For example, the crawler should report that a button contains:

```text
"Reject All"
```

The YAML rule determines whether that observation satisfies the relevant requirement.

---

# Architecture

The project follows a layered architecture.

```text
┌──────────────────────────────────────────────┐
│                  API Layer                   │
│          FastAPI / Request / Response        │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│                Service Layer                 │
│              Scan orchestration              │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│                 Crawler Layer                │
│ Playwright / DOM / Network / Cookies / Store │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│             Observation Models               │
│        Structured crawler observations       │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│                Rule Engine                   │
│ Loader / Validator / Evaluators / Operators  │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│                 YAML Rules                   │
│       Framework-specific configuration       │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│               Check Results                  │
│    PASS / FAIL / WARNING / MANUAL_REVIEW    │
└──────────────────────────────────────────────┘
```

---

# Technology Stack

| Component          | Technology              |
| ------------------ | ----------------------- |
| Language           | Python                  |
| API                | FastAPI                 |
| Data Validation    | Pydantic                |
| Browser Automation | Playwright              |
| Rule Configuration | YAML                    |
| YAML Parsing       | PyYAML                  |
| Database           | PostgreSQL              |
| Queue / Cache      | Valkey                  |
| Testing            | Pytest                  |
| Containerization   | Docker / Docker Compose |

---

# Project Structure

The project is organized to keep API, crawling, domain logic, and rule evaluation separate.

```text
PrivaCheck/
│
├── backend/
│   │
│   ├── api/
│   │   ├── dependencies/
│   │   ├── routes/
│   │   ├── services/
│   │   └── schemas.py
│   │
│   ├── core/
│   │   └── config.py
│   │
│   ├── crawler/
│   │   ├── browser.py
│   │   ├── cookies.py
│   │   ├── dom.py
│   │   ├── links.py
│   │   ├── network.py
│   │   ├── orchestrator.py
│   │   ├── pass_runner.py
│   │   ├── storage.py
│   │   └── two_pass.py
│   │
│   ├── domain/
│   │   ├── checks/
│   │   └── rules/
│   │       └── models.py
│   │
│   ├── rule_engine/
│   │   ├── engine.py
│   │   ├── evaluator.py
│   │   ├── loader.py
│   │   ├── operators.py
│   │   └── evaluators/
│   │
│   └── schemas/
│       └── core.py
│
├── rules/
│   ├── gdpr/
│   │   └── rules.yaml
│   │
│   └── test/
│       └── rules.yaml
│
├── tests/
│   ├── crawler/
│   └── rule_engine/
│
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

# Crawler

The crawler uses **Playwright** to interact with websites in a real browser environment.

The crawler is responsible for collecting observations; it does not make framework-specific compliance decisions.

## Observation types

The current architecture supports observations such as:

```text
cookie
network_request
network_response
dom_form
dom_button
dom_input
dom_visible_text
dom_scripts
dom_layout
link
local_storage
session_storage
indexed_db
```

Observations follow a structured model:

```python
Observation(
    category="dom_button",
    source_url="https://example.com",
    timestamp=...,
    data={
        "text": "Reject All",
        "aria_label": "Reject All"
    }
)
```

This allows the same observation to be consumed by different rules.

---

# Single-Pass Scanning

For rules that only require the website's current state, PrivaCheck uses a normal single-pass scan.

The general flow is:

```text
Open browser
    ↓
Navigate to target
    ↓
Capture network activity
    ↓
Collect DOM observations
    ↓
Collect cookies
    ↓
Collect storage
    ↓
Collect links
    ↓
Return structured observations
```

The common execution path is centralized in the `SinglePassRunner`.

This avoids duplicating browser and collection logic across different scanning workflows.

---

# Two-Pass Scanning

Some compliance checks require comparing the website's behavior under two different user choices.

For example:

```text
Initial State
     │
     ├── Accept
     │      ↓
     │   Capture State A
     │
     └── Reject
            ↓
         Capture State B
```

PrivaCheck implements this through `TwoPassRunner`.

Each pass uses a **fresh browser context** so that state generated during the first pass does not leak into the second pass.

```text
        Two-Pass Runner
              │
       ┌──────┴──────┐
       │             │
       ▼             ▼
Fresh Context    Fresh Context
   ACCEPT           REJECT
       │             │
       ▼             ▼
 Observations    Observations
       │             │
       └──────┬──────┘
              ▼
        State Difference
              │
              ▼
        Rule Evaluation
```

The resulting data can be evaluated with a generic `state_diff` evaluator.

### Missing consent controls

Failure to find a consent control is treated as:

```text
NOT_FOUND
```

rather than automatically treating the entire crawler execution as failed.

The crawler can therefore still return the observations it collected from the page.

---

# Generic Rule Engine

The rule engine is the core of PrivaCheck's configurable architecture.

Its responsibility is to:

1. Load rules from YAML.
2. Validate rule structure.
3. Select the appropriate evaluator.
4. Evaluate observations.
5. Produce a structured `CheckResult`.

The engine currently supports the following evaluator concepts:

```text
declarative
state_diff
visual       (planned)
nlp          (planned)
```

The currently implemented evaluation paths focus on:

* Declarative rule evaluation
* State-difference evaluation

---

# YAML Rule System

Rules are defined outside the Python implementation.

A simplified rule looks like:

```yaml
rules:

  - id: RULE-001

    name: Example rule

    description: >
      Checks whether the required observation exists.

    category: CONSENT

    source:
      observation: dom_button
      match: any

    evaluator: declarative

    conditions:
      any:
        - field: text
          operator: matches
          value: "(?i)example"

        - field: aria_label
          operator: matches
          value: "(?i)example"

    result:
      pass: PASS
      fail: FAIL

    severity: HIGH

    recommendation: >
      Provide the required control.
```

The important idea is that the evaluator does not need to know that this is a specific GDPR rule.

The YAML configuration defines the semantics.

---

# Rule Loading and Validation

The `RuleLoader` is responsible for validating rule definitions before they are used.

Validation covers areas such as:

* Rule structure
* Required fields
* Supported observation types
* Supported evaluators
* Supported source matching modes
* Condition structure
* Duplicate rule IDs
* Pydantic model validation

This prevents malformed configuration from silently reaching the evaluation layer.

---

# Declarative Evaluation

Declarative rules operate on observations and conditions.

For example:

```text
Observation:
    category = dom_button
    text = "Reject All"

Rule:
    field = text
    operator = matches
    value = "Reject All"
```

The evaluator determines whether the observation satisfies the configured conditions.

The resulting check contains:

```text
PASS / FAIL
+
Explanation
+
Severity
+
Evidence
```

---

# State-Difference Evaluation

The state-difference evaluator compares observations from two separate website states.

It is intentionally generic.

For example:

```text
Accept State
    ├── analytics cookie
    ├── session cookie
    └── required cookie

Reject State
    ├── session cookie
    └── required cookie
```

The evaluator can derive:

```text
Accept-only
Reject-only
Common
```

and evaluate configurable assertions such as:

```text
equal
different
accept_subset_of_reject
reject_subset_of_accept
accept_superset_of_reject
reject_superset_of_accept
```

This allows state-based rules to be defined without embedding framework-specific logic into the evaluator.

---

# Compliance Result Model

A rule evaluation produces a structured `CheckResult`.

Conceptually:

```json
{
  "check_id": "RULE-001",
  "name": "Example rule",
  "status": "FAIL",
  "severity": "HIGH",
  "confidence": 0.8,
  "explanation": "Required control was not detected.",
  "recommendation": "Provide the required control.",
  "evidence": []
}
```

The evidence field contains the observations relevant to the evaluation.

This makes the result useful for:

* API responses
* Reports
* Dashboards
* Debugging
* Audit-oriented workflows

---

# API

The API layer is being built with **FastAPI**.

The intended API workflow is:

```text
Client
  ↓
POST /scan
  ↓
Website URL
Framework
  ↓
Scan Service
  ↓
Crawler
  ↓
Rule Engine
  ↓
Results + Evidence
```

The request model is designed around:

```json
{
  "website": "https://example.com",
  "framework": "gdpr"
}
```

The current API implementation is being developed around a service-oriented design so that scan orchestration does not live directly inside FastAPI route handlers.

### Planned response

```json
{
  "website": "https://example.com",
  "framework": "gdpr",
  "status": "PASS",
  "total_checks": 10,
  "passed_checks": 8,
  "failed_checks": 2,
  "observation_count": 125,
  "results": []
}
```

Swagger / OpenAPI will be exposed through FastAPI once the API entrypoint and routes are finalized.

---

# Running the Project

## 1. Clone the repository

```bash
git clone <repository-url>
cd PrivaCheck
```

## 2. Create a virtual environment

### Windows

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### Linux / macOS

```bash
python3 -m venv venv
source venv/bin/activate
```

## 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

## 4. Install Playwright Chromium

```bash
playwright install chromium
```

The Chromium installation is required because the crawler performs browser-based website analysis.

---

# Docker Services

The project includes Docker Compose configuration for infrastructure services.

Current infrastructure includes:

```text
PostgreSQL
Valkey
```

Start the infrastructure with:

```bash
docker compose up -d
```

Check running containers:

```bash
docker compose ps
```

Stop services:

```bash
docker compose down
```

---

# Testing

PrivaCheck uses **Pytest** for automated testing.

Run the complete test suite:

```bash
python -m pytest -v
```

Run crawler tests:

```bash
python -m pytest tests/crawler/ -v
```

Run rule-engine tests:

```bash
python -m pytest tests/rule_engine/ -v
```

The crawler tests cover behavior such as:

* Single-pass execution
* Two-pass execution
* Fresh browser contexts between passes
* Missing consent controls
* Collection workflow behavior

Rule-engine tests cover the configurable rule evaluation architecture.

---

# Development Principles

## Separation of collection and evaluation

The crawler should answer:

> **What happened on the website?**

The rule engine should answer:

> **Does that behavior satisfy the configured rule?**

This separation is one of the most important architectural properties of PrivaCheck.

---

## Configuration over hard-coded logic

Adding or modifying a rule should primarily require changing:

```text
rules/<framework>/rules.yaml
```

rather than changing crawler code.

---

## Evidence-first results

Every failed assessment should provide enough information to understand the reason for the result.

The intended flow is:

```text
Rule
 ↓
Matched observations
 ↓
Evaluation
 ↓
Explanation
 ↓
Recommendation
```

---

## Framework independence

Although GDPR is the initial framework, the rule engine is intended to be framework-agnostic.

The architecture is:

```text
              ┌────────────────┐
              │ Generic Crawler│
              └───────┬────────┘
                      │
              Structured Evidence
                      │
                      ▼
              ┌────────────────┐
              │  Generic Rule  │
              │     Engine     │
              └───────┬────────┘
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
        GDPR       Framework B  Framework C
        YAML          YAML         YAML
```

A different framework can therefore use the same crawler and evaluation infrastructure with a different rule configuration.

---

# Current Development Status

### Implemented

* Playwright-based browser crawling
* Structured observation model
* DOM observation collection
* Cookie collection
* Storage collection
* Link collection
* Network observation collection
* Single-pass crawler workflow
* Two-pass crawler workflow
* Fresh browser contexts for independent passes
* Generic state-difference evaluation
* Declarative rule evaluation
* YAML rule loading
* Rule validation
* Structured compliance results
* Evidence attached to rule results
* Automated crawler and rule-engine tests
* PostgreSQL and Valkey Docker infrastructure

### In Progress

* FastAPI routes
* Scan API
* Swagger / OpenAPI integration
* Complete GDPR rule set
* Persistent scan storage
* Background scan jobs
* Final report generation
* Dashboard / frontend

### Planned

* Visual evaluation
* NLP-based evaluation
* More advanced tracker classification
* Expanded framework support
* Production deployment
* Improved confidence calibration
* Complete end-to-end integration testing

---

# Limitations

PrivaCheck is a **technical web assessment system**, not a replacement for legal advice or a formal legal compliance audit.

A crawler can observe technical website behavior, but some regulatory requirements require:

* Organizational context
* Legal interpretation
* Contractual information
* Internal processing records
* Human review
* Information that is not publicly observable from a website

Therefore, a `PASS` or `FAIL` result should be interpreted as the result of the configured technical assessment rules, not as a definitive legal determination.

---

# Future Architecture

The longer-term architecture is intended to support asynchronous and scalable scans:

```text
                ┌───────────────┐
                │    Client     │
                └───────┬───────┘
                        │
                        ▼
                ┌───────────────┐
                │    FastAPI    │
                └───────┬───────┘
                        │
                        ▼
                ┌───────────────┐
                │   Job Queue   │
                │    Valkey     │
                └───────┬───────┘
                        │
                        ▼
                ┌───────────────┐
                │ Crawler Worker│
                └───────┬───────┘
                        │
                        ▼
                ┌───────────────┐
                │   Analysis    │
                └───────┬───────┘
                        │
                        ▼
                ┌───────────────┐
                │  Rule Engine  │
                └───────┬───────┘
                        │
                        ▼
                ┌───────────────┐
                │   PostgreSQL  │
                └───────┬───────┘
                        │
                        ▼
                ┌───────────────┐
                │ Report / UI   │
                └───────────────┘
```

This design allows expensive browser scans to execute independently from the API process and provides a path toward horizontal scaling.

---

# Example End-to-End Flow

Consider a website containing a consent banner.

The crawler may observe:

```text
dom_button
    text = "Accept All"

dom_button
    text = "Reject All"

cookie
    name = "session_id"

network_request
    url = "https://analytics.example.com/..."
```

The rule engine then evaluates those observations using the YAML configuration.

The final result could contain:

```text
Check ID: GDPR-003
Status: PASS
Severity: HIGH

Explanation:
A visible decline/reject control was detected.

Evidence:
- dom_button: "Reject All"
```

The important point is that the crawler only collected the evidence. The rule definition determined what that evidence means.

---

# Design Philosophy

PrivaCheck is built around four principles:

```text
Observe
   ↓
Structure
   ↓
Evaluate
   ↓
Explain
```

The project therefore aims to move away from a traditional:

```text
if website does X:
    fail GDPR
```

implementation toward:

```text
Website
   ↓
Observable facts
   ↓
Generic rule evaluation
   ↓
Configurable compliance result
```

This makes the platform easier to extend, test, maintain, and adapt to new compliance frameworks.

---

# License

A project license has not yet been finalized.
