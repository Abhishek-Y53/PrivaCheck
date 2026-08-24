# Security Architecture

## 1. Threat Model

The crawler visits URLs provided by potentially untrusted users.

Therefore the crawler itself must be treated as a high-risk component.

## 2. SSRF Protection

The system must prevent requests to:

- localhost
- 127.0.0.0/8
- private IPv4 ranges
- private IPv6 ranges
- link-local addresses
- cloud metadata endpoints
- internal network services

## 3. Protocol Restrictions

Only approved protocols should be allowed.

Initial supported protocol:

https

http may be supported when required for redirect/security analysis.

The following should not be accepted:

- file://
- ftp://
- arbitrary local protocols

## 4. Redirect Validation

A URL must be validated again after every redirect.

A public initial URL must not be allowed to redirect into a private network address.

## 5. Resource Limits

Each scan should enforce:

- Maximum pages
- Maximum crawl depth
- Maximum requests
- Maximum response size
- Maximum redirects
- Maximum scan duration
- Browser timeout

## 6. Browser Isolation

Browser workers should execute in isolated containers/environments.

The crawler should not have unnecessary access to:

- Host filesystem
- Host network
- Cloud credentials
- Internal services

## 7. Input Validation

Validate:

- URL format
- Protocol
- Hostname
- DNS resolution
- Redirect targets

## 8. Rate Limiting

The API should limit excessive scan creation.

The crawler should also respect reasonable target-site request limits.

## 9. Data Protection

The system should avoid storing sensitive user/site data unnecessarily.

Only information required for the scan and report should be retained.