---
id: odepa-row-anomaly-quarantine
date: 2026-09-22
scope: feature
tags: [odepa, data-pipeline, validation, provenance, allowlist]
source: bug-fix
confidence: 0.5
related: ["[[odepa-source-price-invariants]]"]
---

# Quarantine source-confirmed invalid rows by full identity

## Context
An otherwise current annual ODEPA resource failed validation because two 2021 egg-price observations reported a minimum of 980 and a maximum of 2. The confirmed rows were isolated to one date, region, sector, monitoring-point type, product, unit and average value.

## Mistake
The initial row fingerprint assumed week 48 based on a secondary audit summary; the official CSV reported week 47. That overly specific but unverified value caused the exact known rows to continue failing closed.

## Lesson
- For source-confirmed anomalies, allowlist the complete canonical row identity and reported values, never a CSV line number or broad product/range rule.
- Match only after the row passes all non-price checks and fails specifically on the known invariant; any near match or duplicate remains an error. Confirm week number and other fields from the current raw source instead of inferring them from a summary.
- Persist omitted-row provenance alongside the annual resource and publish it so the UI can explain gaps. When ODEPA corrects a row, accept it through normal validation rather than keeping it excluded.

## When to Apply
Use this pattern when a verified upstream data defect blocks a mostly valid annual or batch import, and the product decision is to retain the remaining valid records without silently repairing source values.
