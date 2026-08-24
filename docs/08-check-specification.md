# GDPR Compliance Check Specification

## Source of Truth

This document contains the compliance checks defined for the initial version of the system.

The checks are divided into:

- Group A: Page Load + DOM Scan
- Group B: Network Trace
- Group C: Policy Text/NLP Scan

## Group A

1. Cookie/consent banner exists on first load
2. Consent checkboxes are unticked by default
3. Reject All / decline option exists
4. Consent is granular
5. Marketing consent is separate from ToS
6. Privacy policy is linked and reachable
7. Privacy policy reachable within N clicks
8. DSAR / Data Access Request mechanism exists
9. Data export feature exists
10. Erasure/rectification mechanism exists
11. Objection-to-processing mechanism exists
12. Cookie preference center is accessible
13. Age-gate / age-verification present
14. DPO contact details published
15. Supervisory authority information present
16. Special-category data forms have explicit consent
17. Password fields properly masked
18. No dark-pattern visual imbalance
19. No Cookie Walls / Tracking Walls

## Group B

20. No non-essential cookies set before consent
21. No HTML5 Web Storage set before consent
22. No tracking/analytics requests fired before consent
23. Third-party trackers cross-checked against policy
24. Site served over HTTPS with valid certificate
25. No mixed content on pages with forms
26. Forms submitting personal data POST over HTTPS
27. Security headers present
28. International data transfer signals detected
29. Respects Global Privacy Control

## Group C

30. Policy names the controller
31. Policy states purposes of processing
32. Policy states legal basis per purpose
33. Policy discloses legitimate-interest details
34. Policy lists recipients/categories of recipients
35. Policy discloses international transfers and safeguards
36. Policy states retention period or criteria
37. Policy lists GDPR rights
38. Policy mentions right to withdraw consent
39. Policy mentions right to lodge a complaint
40. Policy states if data provision is mandatory
41. Policy discloses automated decision-making/profiling
42. Policy mentions data breach notification process
43. Policy language readability score
44. Policy available in multiple languages

## Advanced Stateful Testing

The system should use a two-pass crawl:

Pass 1:
Accept State

Pass 2:
Reject State

The browser state is cleared between passes.

The system compares:

- Cookies
- Web storage
- Network requests
- Tracking activity

A difference is used to evaluate whether rejection successfully prevents non-essential tracking.

## Limitations

The crawler does not attempt to automatically determine:

- Actual DSAR response time
- Internal security practices
- Internal legal administration
- Legal validity of legitimate interest
- DPO appointment requirement based on organizational context