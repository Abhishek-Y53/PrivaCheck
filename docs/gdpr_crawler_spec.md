# GDPR Compliance Web Crawler: Feature Specification

**Project Context:** Automated GDPR Compliance Checker (B.Tech 7th Semester Project)
**Architecture:** Headless Browser + Network Trace + DOM/Cookie/Header Inspection + Text Scraping/NLP

This document outlines the subset of GDPR compliance checks that a crawler can deterministically perform without manual human testing, waiting on email responses, or subjective legal judgment calls.

---

## Group A: Detectable via Page Load + DOM Scan
These checks focus on UI/UX elements, accessibility of legal pages, and the presence of mandatory consent mechanisms.

| # | Compliance Check | Implementation Strategy (How) |
|---|---|---|
| 1 | Cookie/consent banner exists on first load | DOM presence check for known banner patterns or CMP scripts (OneTrust, Cookiebot, etc.). |
| 2 | Consent checkboxes are unticked by default | Inspect `checked` attribute on checkbox inputs. |
| 3 | "Reject All" / decline option exists | DOM text/button search near the consent banner. |
| 4 | Consent is granular | Count distinct toggle/checkbox elements in the consent UI (per-category toggles, not one bundled option). |
| 5 | Marketing consent is separate from ToS | DOM inspection of signup/checkout forms ensuring independent checkboxes. |
| 6 | Privacy policy is linked and reachable | Crawl for `href` containing "privacy", verify it resolves (200 HTTP status). |
| 7 | Privacy policy reachable within N clicks | Link-graph traversal depth from the homepage. |
| 8 | DSAR / Data Access Request mechanism exists | Text/link search for "access request", "download my data", or "data subject rights". |
| 9 | Data export feature exists | DOM search for export/download buttons in account settings pages (flag as best-effort if behind login). |
| 10 | Erasure/rectification mechanism exists | Text/link search on privacy/settings pages. |
| 11 | Objection-to-processing mechanism exists | Text/link search for opt-out links. |
| 12 | Cookie preference center is accessible | DOM footer scan for persistent links (e.g., "Cookie Settings") post-consent. |
| 13 | Age-gate / age-verification present | DOM search for date-of-birth fields or age confirmation prompts (applicable if content suggests child-directed service). |
| 14 | DPO contact details published | Text scan of privacy policy/contact page for "Data Protection Officer" + email/contact pattern. |
| 15 | Supervisory authority info present | Text scan for "supervisory authority", "right to lodge a complaint", or DPA name. |
| 16 | Special-category data forms have explicit consent | DOM inspection of forms containing health/religion/biometric field labels, checking for adjacent consent checkbox. |
| 17 | Password fields properly masked | Check `type="password"` attribute on input fields. |
| 18 | No dark-pattern visual imbalance | CSS computed style comparison (size, color contrast, click-depth) between "Accept" and "Reject" buttons (heuristic). |
| 19 | *No Cookie Walls / Tracking Walls* | Check if `<body>` has `overflow: hidden` or fixed overlays preventing interaction before consent. |

---

## Group B: Detectable via Network Trace 
These checks utilize the headless browser's ability to record network requests and monitor storage states.

| # | Compliance Check | Implementation Strategy (How) |
|---|---|---|
| 20 | No non-essential cookies set before consent(cookies.py) | Record `Set-Cookie` headers and `document.cookie` before any consent click is simulated. |
| 21 | *No HTML5 Web Storage set before consent*(storage.py) | Inspect `window.localStorage`, `sessionStorage`, and `IndexedDB` before consent. |
| 22 | No tracking/analytics requests fired before consent(network.py) | Record outbound requests (GA, Meta Pixel, ad networks) before consent interaction. |
| 23 | Third-party trackers cross-checked against policy(text.py) | Domain-match outbound requests against a known tracker list, then keyword-match policy text for vendor names. |
| 24 | Site served over HTTPS with valid certificate(network.py/security.py) | TLS handshake verification. |
| 25 | No mixed content on pages with forms(network.py) | Scan for `http://` resources loaded on an `https://` page. |
| 26 | Forms submitting personal data POST over HTTPS (dom.py) | Inspect form `action` attribute and the actual network request scheme. |
| 27 | Security headers present(network.py) | Inspect response headers for HSTS, CSP, X-Content-Type-Options, etc. |
| 28 | International data transfer signals detected (network.py) | IP/domain geolocation lookup on outbound request destinations to detect non-EU data transfers. |
| 29 | *Respects Global Privacy Control (GPC)* (browser.py) | Send `Sec-GPC: 1` header and monitor if site drops non-essential trackers automatically. |

---

## Group C: Detectable via Text/NLP Scan of Policy Pages
These checks rely on fetching the text of privacy pages, parsing it, and running keyword or NLP embedding matches. (Accuracy is probabilistic).

| # | Compliance Check | Implementation Strategy (How) |
|---|---|---|
| 30 | Policy names the controller | Keyword/Entity extraction (company name, contact details). |
| 31 | Policy states purposes of processing | Keyword match ("purpose", "we use your data to..."). |
| 32 | Policy states legal basis per purpose | Keyword match ("consent", "legitimate interest", "contract", "legal obligation"). |
| 33 | Policy discloses legitimate interest details | Keyword match near "legitimate interest". |
| 34 | Policy lists recipients/categories of recipients | Keyword match ("third parties", "share your data with"). |
| 35 | Policy discloses international transfers & safeguards | Keyword match ("Standard Contractual Clauses", "adequacy decision", "Binding Corporate Rules", "outside the EEA"). |
| 36 | Policy states retention period or criteria | Keyword match ("retain", "how long we keep", specific durations). |
| 37 | Policy lists GDPR rights | Keyword match per right (access, rectification, erasure, restriction, portability, objection). |
| 38 | Policy mentions right to withdraw consent | Keyword match ("withdraw"). |
| 39 | Policy mentions right to lodge a complaint | Keyword match ("lodge a complaint", "supervisory authority"). |
| 40 | Policy states if data provision is mandatory | Keyword match regarding consequences of refusal to provide data. |
| 41 | Policy discloses automated decision-making/profiling | Keyword match ("automated decision", "profiling") and associated logic/consequences. |
| 42 | Policy mentions data breach notification process | Keyword match ("data breach", "notify"). |
| 43 | Policy language readability score | Flesch-Kincaid or similar readability metric on extracted text to ensure it is not overly dense legalese. |
| 44 | Policy available in multiple languages | Compare site `hreflang`/language switcher against available policy translations. |

---

## Advanced Architecture: The "Two-Pass" Crawl (Stateful Testing)
To verify that the "Reject All" button is truly functionally equivalent to "Accept All" (and not a dummy button), the crawler utilizes a two-pass methodology:

1.  **Pass 1 (The Accept State):** Load the page, simulate a click on "Accept All", and record all dropped cookies, web storage items, and third-party network requests.
2.  **Pass 2 (The Reject State):** Clear browser state, reload the page, simulate a click on "Reject All", and record the state.
3.  **Diff Evaluation:** Compare the network and storage footprints of both passes. If tracking scripts fire or tracking cookies are dropped during Pass 2, the site is flagged for a functional consent violation.

---

## Limitations: What is Explicitly Not Crawlable
The following elements require internal auditing, business-context judgment, or physical passage of time, falling outside the scope of an automated crawler:

*   **Actual response time to a DSAR:** Requires submitting a real request and waiting up to 30 days to measure the response.
*   **Internal Security Practices:** Actual encryption-at-rest implementations, backup routines, and server-side configurations.
*   **Internal Legal Administration:** Existence of Data Processing Agreements (DPAs) with vendors, Data Protection Impact Assessments (DPIAs), and internal staff training records.
*   **Legal Validity of "Legitimate Interest":** A crawler can detect if a company *claims* legitimate interest, but cannot perform the legal balancing test to determine if that claim is legally justified.
*   **DPO Requirement Context:** Determining if a company's specific data volume legally requires them to appoint a DPO (which depends on the core business model, not just the website).