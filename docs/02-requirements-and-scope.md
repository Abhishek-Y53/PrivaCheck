# Requirements and Scope

## 1. Functional Requirements

The system shall:

1. Accept a website URL.
2. Validate the submitted URL.
3. Create a scan.
4. Execute the scan asynchronously.
5. Load the target website using a real browser.
6. Inspect the DOM.
7. Inspect cookies.
8. Inspect browser storage.
9. Record network requests.
10. Inspect HTTP response headers.
11. Discover privacy-related pages.
12. Extract privacy-policy text.
13. Run compliance checks.
14. Execute Accept and Reject consent states where possible.
15. Compare browser states between consent passes.
16. Store evidence for each result.
17. Calculate compliance scores.
18. Generate a report.
19. Expose scan status through the API.
20. Display results through the frontend.

## 2. Scan States

A scan should have explicit states:

- CREATED
- QUEUED
- CRAWLING
- CRAWL_COMPLETED
- ANALYZING
- ANALYSIS_COMPLETED
- REPORT_GENERATED
- COMPLETED
- FAILED
- TIMEOUT
- BLOCKED
- INVALID_URL

## 3. Result States

Each compliance check should support:

- PASS
- FAIL
- WARNING
- NOT_APPLICABLE
- NOT_DETECTED
- ERROR

## 4. Check Result Metadata

A check result should contain:

- Check ID
- Check name
- Category
- Status
- Severity
- Confidence
- Evidence
- Explanation
- Recommendation

## 5. Deterministic vs Heuristic Checks

The system must distinguish deterministic checks from heuristic/probabilistic checks.

Example:

`<input type="password">`

can be detected deterministically.

However, interpreting the meaning or adequacy of privacy-policy language may be probabilistic.

Therefore the system should preserve confidence information where appropriate.