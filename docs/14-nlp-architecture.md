# NLP Architecture

## 1. Purpose

The NLP system analyzes privacy-policy pages and extracts evidence related to GDPR requirements.

## 2. Initial Approach

Start with deterministic and lightweight NLP:

- Regex
- Keyword matching
- RapidFuzz
- spaCy
- textstat

## 3. NLP Tasks

The NLP system should support:

- Policy text extraction
- Section identification
- Keyword matching
- Entity extraction
- Legal-basis detection
- Rights detection
- Retention detection
- International-transfer detection
- DPO/contact detection
- Complaint-right detection
- Automated decision/profiling detection
- Readability scoring
- Language detection/comparison

## 4. Semantic Matching

Later introduce:

sentence-transformers

This should be used when exact keyword matching becomes insufficient.

## 5. LLM Policy

An LLM is not required for the first version.

The initial implementation should prioritize:

- Determinism
- Explainability
- Reproducibility
- Low computational cost

## 6. NLP Output

The NLP engine should return structured evidence.

Example:

{
    "document": "privacy-policy",
    "finding": "retention_period",
    "matched_text": "...",
    "confidence": 0.91
}