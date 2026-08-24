# Data and Evidence Model

## 1. Principle

Compliance results must be evidence-backed.

The system should never store only:

PASS / FAIL

It should also store the information used to reach that conclusion.

## 2. Evidence Types

### DOM Evidence

- Page URL
- Element
- Selector
- Text
- Relevant attributes
- Relevant styles

### Network Evidence

- Request URL
- Domain
- Method
- Status code
- Request headers
- Response headers
- Timestamp
- Before/after consent state

### Cookie Evidence

- Cookie name
- Domain
- Path
- Secure
- SameSite
- Timestamp
- Consent state

### Storage Evidence

- Storage type
- Key
- Value metadata
- Before/after consent state

### Policy Evidence

- Policy URL
- Extracted text
- Matching section
- Matching phrase
- Detected entity
- Confidence

## 3. Example Result

{
    "check_id": "GDPR-020",
    "status": "FAIL",
    "severity": "HIGH",
    "confidence": 0.96,
    "evidence": {
        "cookie": "_ga",
        "domain": "google-analytics.com",
        "before_consent": true
    },
    "explanation": "A tracking cookie was detected before consent.",
    "recommendation": "Prevent non-essential tracking cookies from being created before consent."
}

## 4. Evidence Retention

Large artifacts such as:

- Screenshots
- HTML snapshots
- HAR files
- Raw logs

should be stored separately from core relational records when necessary.

The database should store metadata and references to those artifacts.