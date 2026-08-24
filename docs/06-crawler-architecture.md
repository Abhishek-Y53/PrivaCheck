# Crawler Architecture

## 1. Browser Engine

Technology:

Playwright + Chromium

The crawler requires browser-level access because the project needs to inspect:

- DOM
- Cookies
- localStorage
- sessionStorage
- IndexedDB
- Network requests
- Response headers
- Forms
- Consent interfaces
- Dynamically rendered content

## 2. Crawler Components

Crawler Worker
│
├── Browser Manager
├── Page Loader
├── DOM Collector
├── Network Collector
├── Cookie Collector
├── Storage Collector
├── Header Collector
├── Link Extractor
├── Policy Page Detector
├── Consent Detector
└── Two-Pass Runner

## 3. Browser Manager

Responsible for:

- Browser lifecycle
- Context creation
- Page creation
- Browser state reset
- Timeouts
- Resource limits

## 4. DOM Collector

Responsible for extracting:

- Elements
- Buttons
- Checkboxes
- Forms
- Links
- Visible text
- Attributes
- Relevant CSS/computed properties

## 5. Network Collector

Responsible for recording:

- Request URL
- Request method
- Request headers
- Response status
- Response headers
- Initiator where available
- Timing
- Domain
- Protocol

## 6. Cookie Collector

Responsible for:

- Set-Cookie headers
- Browser cookies
- Cookie names
- Domains
- Paths
- Secure flag
- SameSite
- Timing

## 7. Storage Collector

Inspect:

- localStorage
- sessionStorage
- IndexedDB

The collector must support snapshots before and after consent actions.

## 8. Link Discovery

The crawler should discover:

- Privacy policy
- Cookie policy
- Terms
- Data-subject-rights pages
- Contact/DPO pages
- Preference centers

## 9. Crawler Limits

Every scan should have configurable limits:

- Maximum pages
- Maximum crawl depth
- Maximum requests
- Maximum response size
- Maximum redirects
- Maximum scan duration
- Browser timeout

## 10. Crawler Output

The crawler should generate observations rather than compliance decisions.

Example:

{
    "type": "cookie_created",
    "name": "_ga",
    "domain": "example.com",
    "before_consent": true
}

The compliance engine evaluates this observation later.
