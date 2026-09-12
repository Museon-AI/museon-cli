# Changelog

Museon CLI follows semantic versioning for its package and command contract.

## 0.6.0

- Replaced the former AI Hook public domain with `hireaicreator`, exposing 45 commands including read-only item and batch history queries.
- Added `media` upload, import, read, generation, and status commands with explicit idempotency and billing boundaries.
- Added `ai-slideshow` with 32 asset, generation, publish configuration, version, scheduling, and batch publishing commands.
- Kept 13 selected `social-account` commands and retired the former account-operation, account-publish, asset, generation, product, evaluator, and agentic-campaign top-level domains.
- Consolidated the public Agent Skills into five packages: base, research, HireAICreator, AI Slideshow, and campaign monitor.
- Kept artifacts, routines, content analysis, media, and social-account atomic guidance under the base Skill, while preserving research and campaign monitoring as separate workflows.
