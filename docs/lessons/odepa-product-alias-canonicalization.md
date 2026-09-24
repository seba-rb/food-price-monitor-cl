---
id: odepa-product-alias-canonicalization
date: 2026-09-22
scope: feature
tags: [odepa, sqlite, product-identity, aliases, data-pipeline]
source: bug-fix
confidence: 0.5
related: []
---

# Canonicalize product labels at publication, not during import

## Context
ODEPA's product labels changed formatting over time, so exact source identities
created separate catalog entries and interrupted otherwise continuous histories.

## Mistake
Treating every source label as a distinct public product hid history, while
broad fuzzy matching produced unsafe candidates across grades, sizes, colors,
and cultivars.

## Lesson
- Retain original product identities and observations in the source database;
  build a separate canonical catalog for publication.
- Normalize only known cosmetic differences, and require explicit reviewed
  rules for semantic aliases.
- Before merging, reject aliases that overlap on week, region, sector, and point
  type so the same source observation cannot be counted twice.
- Publish alternate labels with the canonical product so search can find old
  names without erasing source provenance.

## When to Apply
Apply when an upstream catalog renames or reformats entities and historical
records must remain continuous without mutating the source data.
