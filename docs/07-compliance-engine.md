# Compliance Engine

## 1. Purpose

The compliance engine converts crawler observations into GDPR-related check results.

## 2. Rule Architecture

Every rule should implement a common interface.

Example:

class ComplianceCheck:

    check_id
    name
    category

    def evaluate(self, evidence):
        ...

## 3. Rule Groups

### Group A

DOM and consent-related checks.

### Group B

Network, storage, transport, and security checks.

### Group C

Privacy-policy text/NLP checks.

## 4. Rule Independence

Each compliance rule should be independently testable.

A rule should not directly:

- Launch a browser
- Crawl a website
- Make network requests
- Modify scan state

Instead it consumes collected evidence.

## 5. Rule Registry

A central registry should expose all available compliance rules.

Example:

GDPR-001
GDPR-002
...
GDPR-044

The registry should make adding future checks straightforward.

## 6. Rule Output

Every rule returns a standardized result:

{
    "check_id": "...",
    "status": "...",
    "severity": "...",
    "confidence": 0.0,
    "evidence": {},
    "explanation": "...",
    "recommendation": "..."
}

## 7. Confidence

Deterministic checks may have high confidence.

Heuristic/NLP checks should expose confidence values.

The system must not present heuristic findings as absolute legal conclusions.

## 8. Evidence-First Design

Every failure or warning should have associated evidence.

Examples:

- DOM selector
- Element text
- URL
- Network request
- Cookie name
- Header
- Policy text fragment
- Matched keywords
- Confidence score