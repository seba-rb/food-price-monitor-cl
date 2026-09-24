---
id: odepa-source-price-invariants
date: 2026-09-22
scope: feature
tags: [odepa, data-validation, price-parser, source-quality]
source: bug-fix
confidence: 0.5
related: []
---

# Validate only declared ODEPA price invariants

## Context
During the historical ODEPA import, a legitimate fixture had `Precio promedio` above the reported maximum, while a live 2019 record had its minimum above its maximum. The data model constrains nonnegative values and `minimum <= maximum`, but does not constrain the average to that range.

## Mistake
Treating `average > maximum` as invalid would reject source data beyond the written contract; weakening the parser without checking the source would also risk accepting a genuinely inverted minimum/maximum range.

## Lesson
- Mirror the declared invariant exactly: minimum and average are nonnegative, and maximum is greater than or equal to minimum. Do not infer `average <= maximum` unless the specification adds that rule.
- Reject an inverted minimum/maximum row without silently swapping or dropping values; include product, week, region, sector, and point type in the validation error.
- Confirm anomalous records against ODEPA's DataStore when possible, then keep the annual transaction and public publication fail-closed.

## When to Apply
When changing ODEPA CSV normalization, price validation, or refresh handling for malformed source rows.
