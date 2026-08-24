# GDPR Compliance Web Crawler

## 1. Project Overview

The project is an automated GDPR compliance assessment platform that accepts a website URL and evaluates the website against a defined set of GDPR-related checks.

The system uses automated browser interaction, network inspection, DOM inspection, cookie/storage analysis, HTTP/security-header inspection, and privacy-policy text/NLP analysis.

The system should provide:

- Automated compliance assessment
- Individual check results
- Evidence supporting each result
- Compliance score
- Warnings and failures
- Recommendations for improvement
- A final report

The system must distinguish between:

1. What can be automatically detected
2. What can only be detected heuristically
3. What cannot be determined automatically

The system must not claim that a website is legally GDPR compliant solely based on automated crawling.

## 2. Primary Goal

Build a scalable automated system capable of analyzing a website and producing an evidence-backed GDPR compliance assessment.

## 3. Core Technical Idea

The system follows this pipeline:

User
→ API
→ Scan Orchestrator
→ Queue
→ Crawler Worker
→ Observations
→ Compliance Engine
→ NLP Engine
→ Results
→ Report Generator
→ Frontend

## 4. Architectural Principle

The crawler determines:

"What happened?"

The compliance engine determines:

"Does what happened satisfy this compliance check?"

Therefore:

Crawler
→ Observation
→ Compliance Rule
→ Check Result

The crawler must not contain GDPR compliance decisions directly.

## 5. Initial Scope

The initial crawler will implement the checks defined in the project's feature specification.

These checks cover:

- UI/UX and consent mechanisms
- Network and storage behavior
- Security and transport behavior
- Privacy-policy content
- Consent state changes
- Website behavior before and after consent

## 6. Explicit Limitations

The automated crawler cannot determine:

- Actual DSAR response time
- Internal encryption-at-rest implementation
- Internal backup practices
- Data Processing Agreements
- Data Protection Impact Assessments
- Internal staff training
- Legal validity of legitimate-interest balancing
- Whether a specific organization legally requires a DPO

Such limitations are defined by the project specification.