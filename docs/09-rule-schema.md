# Rule Schema

## 1. Purpose

The Rule Schema defines the structure of configurable compliance rules used by the PrivaCheck rule engine.

Rules are stored outside the application code in YAML files.

The same rule engine must be able to evaluate different rule sets without changing the engine implementation.

Example rule sets:

```text
rules/
├── gdpr/
│   └── rules.yaml
├── security/
│   └── rules.yaml
└── accessibility/
    └── rules.yaml
```

The YAML file defines **what should be checked**.

The Python rule engine defines **how the rule is interpreted and executed**.

---

# 2. Rule Structure

A rule has the following structure:

```yaml
- id: RULE-001
  name: Rule name
  description: Description of the rule

  category: SECURITY

  source:
    observation: network_request
    match: all

  evaluator: declarative

  conditions:
    all:
      - field: protocol
        operator: equals
        value: https

  result:
    pass: PASS
    fail: FAIL

  severity: HIGH

  recommendation: Recommendation text
```

---

# 3. Rule Fields

## 3.1 `id`

A unique identifier for the rule.

Examples:

```text
GDPR-001
SECURITY-001
ACCESSIBILITY-001
```

The rule engine treats the ID as an identifier only.

The engine must not contain framework-specific logic such as:

```text
if rule_id == "GDPR-001"
```

---

## 3.2 `name`

Human-readable name of the rule.

Example:

```yaml
name: HTTPS is required
```

This is used in results and reports.

---

## 3.3 `description`

Human-readable explanation of what the rule checks.

Example:

```yaml
description: All observed network requests must use HTTPS.
```

---

## 3.4 `category`

Describes the general category of the rule.

Examples:

```text
SECURITY
CONSENT
COOKIES
NETWORK
POLICY
ACCESSIBILITY
PRIVACY
```

The category is metadata and should not contain the rule's evaluation logic.

---

# 4. Source

The `source` section identifies the observation type that provides the data required by the rule.

Example:

```yaml
source:
  observation: network_request
```

Available observation categories are defined by the Observation Model.

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

---

# 5. Observation Matching

The source can specify how multiple observations should be considered.

```yaml
source:
  observation: network_request
  match: all
```

Supported initial values:

### `all`

Every matching observation must satisfy the rule conditions.

Example:

```text
Request 1 → HTTPS
Request 2 → HTTPS
Request 3 → HTTPS

Result → PASS
```

If one fails:

```text
Request 1 → HTTPS
Request 2 → HTTP
Request 3 → HTTPS

Result → FAIL
```

### `any`

At least one matching observation must satisfy the conditions.

Example:

```text
Request 1 → HTTP
Request 2 → HTTPS
Request 3 → HTTPS

Result → PASS
```

because at least one observation matches.

Additional aggregation strategies may be added later when an actual rule requires them.

---

# 6. Evaluator

The `evaluator` field specifies the evaluation mechanism.

Initial evaluator types:

```text
declarative
state_diff
visual
nlp
```

## 6.1 Declarative

Used for field-based rules.

Example:

```yaml
evaluator: declarative
```

The engine evaluates fields using operators and values defined in the rule.

---

## 6.2 State Diff

Used when evaluation requires comparison between multiple browser states.

Example:

```yaml
evaluator: state_diff
```

Typical use:

```text
Accept State
      ↓
Observations

Reject State
      ↓
Observations

      ↓

Difference Evaluation
```

---

## 6.3 Visual

Used when the rule depends on visual or layout properties.

Example:

```yaml
evaluator: visual
```

Typical use:

* Element dimensions
* Position
* Style comparisons
* UI imbalance analysis

---

## 6.4 NLP

Used when the rule depends on language or policy text.

Example:

```yaml
evaluator: nlp
```

Typical use:

* Policy concepts
* Entity detection
* Semantic matching
* Readability

---

# 7. Conditions

Declarative rules contain conditions.

Each basic condition has:

```yaml
- field: protocol
  operator: equals
  value: https
```

The three components are:

```text
field
operator
value
```

---

# 8. Field

`field` identifies the data within an observation.

Example:

```yaml
field: protocol
```

For nested objects, dot notation is used.

Example:

```yaml
field: headers.strict-transport-security
```

This represents a path such as:

```text
data
 └── headers
      └── strict-transport-security
```

The rule engine is responsible for resolving the field path.

---

# 9. Operators

The initial operator set is:

```text
equals
not_equals
contains
not_contains
starts_with
ends_with
exists
not_exists
matches
greater_than
less_than
in
not_in
```

Examples:

```yaml
field: protocol
operator: equals
value: https
```

```yaml
field: text
operator: contains
value: Privacy Policy
```

```yaml
field: headers.strict-transport-security
operator: exists
value: true
```

Operators should remain generic and should not contain GDPR-specific logic.

---

# 10. Logical Conditions

Conditions can be combined using:

```text
all
any
```

### `all`

All conditions must be true.

```yaml
conditions:
  all:
    - field: protocol
      operator: equals
      value: https

    - field: method
      operator: equals
      value: POST
```

Equivalent conceptually to:

```text
Condition A AND Condition B
```

### `any`

At least one condition must be true.

```yaml
conditions:
  any:
    - field: text
      operator: contains
      value: privacy

    - field: text
      operator: contains
      value: data protection
```

Equivalent conceptually to:

```text
Condition A OR Condition B
```

`not` may be introduced when a real rule requires it.

---

# 11. Result

The `result` section defines the result produced when the rule passes or fails.

Example:

```yaml
result:
  pass: PASS
  fail: FAIL
```

The result values correspond to the application's result/status model.

Additional states such as:

```text
WARNING
MANUAL_REVIEW
NOT_APPLICABLE
```

may be supported later when required by the rule model.

---

# 12. Severity

Severity describes the importance of a failed rule.

Allowed values are:

```text
CRITICAL
HIGH
MEDIUM
LOW
INFO
```

Example:

```yaml
severity: HIGH
```

Severity is part of the rule definition and is returned with the rule result.

---

# 13. Recommendation

A rule can define a recommendation to be shown when the rule fails.

Example:

```yaml
recommendation: Serve all website resources over HTTPS.
```

The rule engine returns the configured recommendation rather than generating framework-specific remediation text.

---

# 14. Complete Example

```yaml
rules:

  - id: SECURITY-001
    name: HTTPS is required
    description: All observed network requests must use HTTPS.

    category: SECURITY

    source:
      observation: network_request
      match: all

    evaluator: declarative

    conditions:
      all:
        - field: protocol
          operator: equals
          value: https

    result:
      pass: PASS
      fail: FAIL

    severity: HIGH

    recommendation: Serve website resources over HTTPS.
```

---

# 15. Dynamic Rule Principle

The rule engine must not contain rules directly in Python.

Incorrect:

```text
Python code
    ↓
GDPR-001
GDPR-002
GDPR-003
```

Correct:

```text
YAML
    ↓
Rule Loader
    ↓
Validated Rule
    ↓
Generic Rule Engine
    ↓
Observations
    ↓
Result
```

This allows the rule set to be changed without changing the core evaluation engine.

---

# 16. Rule Validation

YAML files must be validated before execution.

The loader should verify:

* Required fields exist
* Rule IDs are unique
* Observation categories are valid
* Evaluator types are valid
* Operators are supported
* Severity values are valid
* Condition structure is valid
* Result structure is valid

Invalid rules should fail during loading rather than causing unpredictable behavior during a scan.

---

# 17. Rule Set Independence

A rule set is simply a collection of rules.

Example:

```text
rules/gdpr/rules.yaml
```

contains GDPR-related rules.

Another file:

```text
rules/security/rules.yaml
```

can contain security-related rules.

The same rule engine loads either rule set.

The Python engine must not contain framework-specific assumptions.

---

# 18. Rule Engine Boundary

The rule engine consumes:

```text
Crawler observations
+
Analysis/enriched observations
+
Selected YAML rule set
```

and produces:

```text
CheckResult
```

The complete flow is:

```text
Crawler
   ↓
Observations
   ↓
Analysis / Enrichment
   ↓
Rule Loader
   ↓
Validated YAML Rules
   ↓
Rule Engine
   ↓
Check Results
```

The rule engine does not directly control browser execution.
