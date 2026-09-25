# Observation Model

## 1. Purpose

The Observation Model defines the contract between the crawler and the rest of the PrivaCheck system.

The crawler is responsible for collecting raw information from a target website.

The crawler does not determine whether the collected information is compliant or non-compliant.

The flow is:

```text
Website
   ↓
Crawler
   ↓
Observations
   ↓
Analysis / Enrichment
   ↓
Rule Engine
   ↓
Check Results
```

The observation model therefore defines:

* What an observation represents
* What observation categories exist
* What data each category provides
* Which crawler component produces each category
* What the rule engine can expect from the crawler

---

# 2. Observation Envelope

All crawler observations use a common structure:

```text
Observation
├── category
├── source_url
├── timestamp
└── data
```

## 2.1 `category`

Identifies the type of observation.

Examples:

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

The category allows the analysis and rule-engine layers to determine what kind of data they are receiving.

---

## 2.2 `source_url`

Identifies the page URL from which the observation was collected.

Example:

```text
https://example.com/privacy
```

This allows an observation to be traced back to the page where it was detected.

---

## 2.3 `timestamp`

Records when the observation was collected.

The timestamp is useful for:

* Ordering observations
* Comparing events
* Stateful analysis
* Future consent-state analysis
* Debugging

---

## 2.4 `data`

Contains the actual information collected by the corresponding crawler component.

The structure of `data` depends on the observation category.

The crawler should store only the information required by the defined compliance/analysis requirements.

---

# 3. Observation Categories

## 3.1 Cookie Observation

### Category

```text
cookie
```

### Source

```text
cookies.py
```

### Required data

```text
name
domain
path
secure
httpOnly
sameSite
expires
```

### Purpose

Provides browser-cookie information for analysis of:

* Cookie presence
* Cookie properties
* Cookie domains
* Consent-state behavior
* Tracking-related cookie evidence

The cookie collector does not determine whether a cookie is essential, non-essential, or compliant.

---

# 3.2 Network Request Observation

### Category

```text
network_request
```

### Source

```text
network.py
```

### Required data

```text
request_id
url
hostname
protocol
method
headers
resource_type
is_navigation_request
```

### Purpose

Provides information about outbound browser requests.

This supports analysis of:

* Third-party requests
* Tracking requests
* HTTP/HTTPS behavior
* Resource types
* Request destinations
* Consent-state network behavior

---

# 3.3 Network Response Observation

### Category

```text
network_response
```

### Source

```text
network.py
```

### Required data

```text
request_id
url
hostname
protocol
status
headers
status_text
```

### Purpose

Provides information about responses received by the browser.

The `request_id` is shared with the corresponding network request observation so that the request and response can be correlated.

This supports analysis of:

* Response status
* Security headers
* HTTPS
* Mixed-content evidence
* Response behavior

---

# 3.4 DOM Form Observation

### Category

```text
dom_form
```

### Source

```text
dom.py
```

### Required data

```text
action
method
controls[]
```

Each form control provides only the metadata required for analysis.

Possible control data includes:

```text
tag
type
name
id
required
checked
label
```

Input values are not collected as part of the DOM observation contract.

### Purpose

Supports analysis of:

* Forms
* Consent controls
* Special-category data fields
* Marketing consent
* Terms of Service controls
* Password fields
* Personal-data form submission

---

# 3.5 DOM Button Observation

### Category

```text
dom_button
```

### Source

```text
dom.py
```

### Required data

```text
text
id
class_name
role
aria_label
visible
position
styles
```

### Purpose

Supports analysis of:

* Consent buttons
* Reject buttons
* Cookie preference controls
* Other relevant UI controls
* Visual comparison between controls

The DOM collector records the button properties but does not decide whether the button represents a valid consent or rejection mechanism.

---

# 3.6 DOM Input Observation

### Category

```text
dom_input
```

### Source

```text
dom.py
```

### Required data

```text
tag
type
name
id
required
checked
label
```

### Purpose

Supports analysis of:

* Checkboxes
* Radio buttons
* Password fields
* Age/date-of-birth fields
* Special-category data fields
* Other form controls

Actual user-entered values are not collected.

---

# 3.7 DOM Visible Text Observation

### Category

```text
dom_visible_text
```

### Source

```text
dom.py
```

### Required data

```text
text
```

### Purpose

Provides visible webpage text that can later be used by:

* Text analysis
* Policy discovery
* NLP
* Rule evaluation

The DOM collector extracts the text but does not interpret its meaning.

---

# 3.8 DOM Script Observation

### Category

```text
dom_scripts
```

### Source

```text
dom.py
```

### Required data

```text
src
```

### Purpose

Provides script source URLs that may be used to identify relevant browser functionality, including known consent-management platforms.

The crawler only records the script source.

Classification is performed outside the collector.

---

# 3.9 DOM Layout Observation

### Category

```text
dom_layout
```

### Source

```text
dom.py
```

### Required data

```text
body_overflow
body_overflow_x
body_overflow_y
fixed_elements[]
```

Relevant fixed-element information includes:

```text
tag
id
class_name
z_index
opacity
width
height
```

### Purpose

Provides layout information required for later analysis of:

* Interaction blocking
* Cookie/tracking walls
* Visual UI differences
* Other layout-based heuristics

This data is evidence only. It does not itself establish a dark pattern or tracking wall.

---

# 3.10 Link Observation

### Category

```text
link
```

### Source

```text
links.py
```

### Required data

```text
href
text
aria_label
```

### Purpose

Provides information about links discovered on the current page.

This supports:

* Privacy-policy discovery
* Data-rights page discovery
* Cookie-policy discovery
* Cookie-preference page discovery
* DPO/contact page discovery
* Other relevant page discovery
* Link-graph construction

`links.py` does not determine the meaning of a link or perform compliance analysis.

---

# 3.11 Local Storage Observation

### Category

```text
local_storage
```

### Source

```text
storage.py
```

### Required data

```text
storage_type
key
value
```

### Purpose

Provides observations of browser `localStorage`.

This information can later be evaluated against rules involving:

* Browser storage
* Consent-state behavior
* Tracking/storage behavior

---

# 3.12 Session Storage Observation

### Category

```text
session_storage
```

### Source

```text
storage.py
```

### Required data

```text
storage_type
key
value
```

### Purpose

Provides observations of browser `sessionStorage`.

The observation is raw storage information and does not contain any compliance judgment.

---

# 3.13 IndexedDB Observation

### Category

```text
indexed_db
```

### Source

```text
storage.py
```

### Required data

```text
storage_type
database
object_store
key
value
```

### Purpose

Provides observations of browser IndexedDB data.

This completes the browser-storage sources required by the crawler.

---

# 4. Crawler Component Mapping

| Crawler component | Observation categories                                                                 |
| ----------------- | -------------------------------------------------------------------------------------- |
| `browser.py`      | Provides browser environment and state used by other collectors                        |
| `network.py`      | `network_request`, `network_response`                                                  |
| `cookies.py`      | `cookie`                                                                               |
| `storage.py`      | `local_storage`, `session_storage`, `indexed_db`                                       |
| `dom.py`          | `dom_form`, `dom_button`, `dom_input`, `dom_visible_text`, `dom_scripts`, `dom_layout` |
| `links.py`        | `link`                                                                                 |
| `two_pass.py`     | Coordinates observations across different browser states                               |

`browser.py` does not directly produce a normal observation category. Its main responsibility is browser lifecycle and isolated browser-context management.

`two_pass.py` does not replace the individual collectors. It coordinates them under controlled browser states.

---

# 5. Observation Design Principles

## 5.1 Observation vs Interpretation

An observation answers:

> What was found?

A rule answers:

> What does that finding mean?

Example:

```text
Observation:

cookie
name = "_ga"
domain = ".google.com"
```

The observation does not say:

```text
FAIL
```

The rule engine determines that later.

---

## 5.2 No Compliance Logic in Collectors

Crawler collectors must not contain logic such as:

```text
is_gdpr_violation
is_compliant
is_tracking_cookie
is_essential
```

Collectors should only collect evidence.

---

## 5.3 No Unnecessary Data

Each collector should collect only information required by:

* Current compliance requirements
* Analysis requirements
* Future state comparison where explicitly required

Unnecessary personal data should not be collected merely because it is technically available.

Examples include:

* User-entered form values
* Unnecessary POST bodies
* Unrelated page data

---

## 5.4 Traceability

Every observation should be traceable to its source page using:

```text
source_url
```

and should record when it was collected using:

```text
timestamp
```

Future scan-state modeling will additionally associate observations with the relevant scan/pass/page-visit context.

---

# 6. Observation Contract and Dynamic Rules

The observation model is the boundary between the generic crawler and the rule engine.

The rule engine should not depend on Playwright APIs directly.

Instead:

```text
Playwright
   ↓
Crawler
   ↓
Observation Contract
   ↓
Analysis / Enrichment
   ↓
Rule Engine
```

This allows the rule engine to remain independent from the browser implementation.

For example, a future YAML rule may refer to:

```text
source: network_response
field: headers.strict-transport-security
operator: exists
```

The rule engine does not need to know that the value came from Playwright.

---

# 7. Current Schema Version

The current observation contract is considered:

```text
Observation Schema v1
```

Changes to the structure of existing observation categories should be treated carefully because external YAML rules will depend on these fields.

Incompatible changes should result in a schema-version update rather than silently changing the meaning of existing fields.

---

# 8. Data Flow

The complete current crawler flow is:

```text
Target URL
    ↓
BrowserManager
    ↓
Browser Context + Page
    ↓
┌────────────┬────────────┬────────────┬────────────┐
│   DOM      │  Network   │   Cookies  │  Storage   │
│            │            │            │            │
│ dom.py     │ network.py │ cookies.py │ storage.py │
└────────────┴────────────┴────────────┴────────────┘
                 │
                 ▼
             links.py
                 │
                 ▼
           Observations
                 │
                 ▼
          CrawlerResult
                 │
                 ▼
        Analysis / Enrichment
                 │
                 ▼
           Generic Rule Engine
                 │
                 ▼
            Check Results
                 │
                 ▼
               Report
```

---

# 9. Future Stateful Observations

The current observation contract is designed so that observations can later be associated with specific scan states.

For example:

```text
Initial
Accept
Reject
GPC
```

The future stateful crawler can therefore produce:

```text
Accept
    ↓
Network observations
Cookie observations
Storage observations

Reject
    ↓
Network observations
Cookie observations
Storage observations
```

The state itself should be supplied by the crawler orchestration layer rather than embedding compliance decisions inside each collector.

---

# 10. Summary

The crawler is responsible for producing reliable, structured evidence.

```text
DOM       → webpage structure and UI evidence
Network   → request/response evidence
Cookies   → cookie evidence
Storage   → browser-storage evidence
Links     → navigation and page-discovery evidence
Browser   → browser lifecycle and state
Two-Pass  → controlled stateful collection
```

The crawler does not decide compliance.

The generic rule engine consumes these observations and evaluates whichever rule set is currently selected.
