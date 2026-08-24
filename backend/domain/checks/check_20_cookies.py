from typing import List
from backend.schemas.core import Observation, CheckResult, ComplianceStatus, SeverityLevel

class CookieConsentCheck:
    """
    Check 20: No non-essential cookies set before consent.
    """
    
    def __init__(self):
        self.check_id = "GDPR-020"
        self.name = "No non-essential cookies set before consent"
    
    def evaluate(self, observations: List[Observation]) -> CheckResult:
        # Filter down to only cookie observations
        cookie_obs = [obs for obs in observations if obs.category == "cookie"]
        
        # Look for suspicious cookies (e.g., ones with long lifespans)
        suspicious_cookies = []
        for obs in cookie_obs:
            cookie_data = obs.data
            # A simple heuristic: if it has an expiration date, flag it for review
            # (In a real production app, we would cross-reference a database of known trackers)
            if "expires" in cookie_data and cookie_data["expires"] > -1:
                suspicious_cookies.append(obs)
                
        # Determine the final result
        if not suspicious_cookies:
            return CheckResult(
                check_id=self.check_id,
                name=self.name,
                status=ComplianceStatus.PASS,
                severity=SeverityLevel.INFO,
                confidence=1.0,
                explanation="No long-lived cookies were found before consent.",
                evidence=[]
            )
        else:
            return CheckResult(
                check_id=self.check_id,
                name=self.name,
                status=ComplianceStatus.FAIL,
                severity=SeverityLevel.HIGH,
                confidence=0.8,
                explanation=f"Found {len(suspicious_cookies)} potentially non-essential cookies set before consent.",
                recommendation="Ensure all tracking and analytics cookies are blocked until the user explicitly clicks 'Accept'.",
                evidence=suspicious_cookies
            )

# --- Quick Test Script ---
if __name__ == "__main__":
    # We can create fake data to test our rule WITHOUT needing to launch a browser!
    # This makes our code highly testable (Unit Testing).
    fake_observations = [
        Observation(
            category="cookie",
            source_url="https://test.com",
            timestamp=123.0,
            data={"name": "tracker_id", "value": "xyz", "expires": 9999999999}
        )
    ]
    
    rule = CookieConsentCheck()
    result = rule.evaluate(fake_observations)
    print(result.model_dump_json(indent=2))
