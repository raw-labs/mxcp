# Pydantic v2 Migration Strategy

This document describes a staged plan to converge all MXCP configuration and definition models on Pydantic v2. The focus is on incremental, low-risk rollouts—starting with site configuration (the “root” dependency) and expanding to additional schemas over time.

---

## Guiding Principles
- **Single source of truth**: Pydantic models (with `model_json_schema()` exports if needed) become the canonical definition. Legacy JSON Schema files are deleted only after their equivalents can be auto-generated.
- **Immutable consumer view**: Once validated, configs should be immutable (`frozen=True`) to discourage incidental mutation. Derived values and defaults live inside model validators.
- **Bridge period**: Loader functions may return both models and dicts temporarily to avoid flag days. Downstream modules gradually adopt model instances and drop `.get()` patterns.
- **Tight feedback**: Each phase ships with targeted tests (unit + integration) that exercise both success and failure scenarios, including environment interpolation.
- **No CLI regression**: Existing CLI commands (`mxcp log`, `mxcp log-cleanup`, etc.) must keep current names, options, and output.

---

## Phase 0 – Preparation
1. **Inventory + ownership**
   - Confirm all call sites of `SiteConfig` / `UserConfig` TypedDicts and jsonschema validation to understand migration blast radius.
   - Establish owners for each schema domain (site, user, endpoints, prompts, evals) so follow-on phases stay staffed.
2. **Decide on doc export**
   - If external tooling still needs JSON Schema files, agree on generating them via `BaseModel.model_json_schema()` to avoid drift.
3. **Define common utilities**
   - Draft helpers for repo-relative path resolution, environment overrides, and profile-specific defaults so they can be reused by later phases.

Deliverables: short design doc for the `SiteConfigModel` API surface, agreement on schema export strategy, and tickets for each migration phase.

---

## Phase 1 – Site Configuration (root dependency)
1. **Model definition**
   - Create `mxcp/server/core/config/models.py` (new names, e.g., `SiteConfigModel`, `SitePathsConfigModel`, etc.).
   - Encode current JSON schema semantics via field types, `Annotated` constraints, and default values in `Field(...)`.
   - Add `model_validator(mode="after")` hooks for derived defaults (DuckDB path, drift/audit files, env overrides). Centralize the logic currently found in `_apply_defaults`.
   - Set `model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=True)` to block stray keys and deliver immutable instances.
2. **Loader bridge**
   - Update `load_site_config` to:
     - Parse YAML → dict
     - Run legacy JSON Schema validation (optional, behind a feature flag) for a release or two
     - Instantiate `SiteConfigModel`
     - Return both the model and `model_dump()` (e.g., `(model, model_dump)` or maintain current signature while storing the model internally)
   - Emit warnings when downstream code accesses dict interfaces so we can track migration progress.
3. **Adopt model consumers**
   - Prioritize modules closest to configuration loading (e.g., `mxcp/server/services/endpoints/service.py`, `.../dbt/runner.py`, `.../executor/engine.py`) to accept the model. Replace `.get()`/`["key"]` operations with dot access.
   - Update tests that rely on plain dict fixtures to instantiate the model instead, or call `model_dump()` explicitly when dicts are required for serialization.
4. **Validation & regression**
   - Add new unit tests for `SiteConfigModel` covering: missing sections, repo-root derived paths, env overrides, invalid values, immutability.
   - Run `uv run pytest tests/server/test_site_config*.py` (create if needed) plus existing integration suites touched by config loading.
5. **Cleanup**
   - Once all runtime code uses the model (no dict consumers remain), delete the `SiteConfig` TypedDict and JSON schema, remove `jsonschema` dependency from this path, and simplify loader return values to just the model.

Exit criteria: `load_site_config` returns only `SiteConfigModel`, no dict-style access in server modules, and JSON schema file `mxcp-site-schema-1.json` is removed (or auto-generated from the model).

---

## Phase 2 – User Configuration
**Prerequisite**: Site config consumers operate purely on `SiteConfigModel`.

1. **Model definition**
   - Introduce `UserConfigModel` and nested components, mirroring the existing schema plus resolver-specific defaults (vault, 1password, transport, telemetry, etc.).
   - Capture dependencies on site config explicitly where required (e.g., default generation uses `SiteConfigModel` values).
2. **Resolver integration**
   - Ensure interpolation (`interpolate_all` / `interpolate_selective`) happens before model validation. Any exceptions raised should reference model fields for clarity.
3. **Loader bridge + adoption**
   - Mirror the site-config strategy: loader returns both model and dict until consumers are migrated.
   - Update CLI initialization and executor setup to consume the model. Replace `TypedDict` imports globally.
4. **Testing & cleanup**
   - Expand `tests/server/test_user_config.py` to instantiate the new model, covering env/file/vault/1password references, persistence defaults, telemetry toggles, etc.
   - Remove `mxcp-config-schema-1.json` and the `UserConfig` TypedDict once adoption is complete.

Exit criteria: `load_user_config` returns only `UserConfigModel`, resolver pipeline validated via tests, and no modules mutate the user config post-validation.

---

## Phase 3 – Definition Schemas (endpoints, prompts, resources, evals)
1. **Prioritize endpoints**
   - Replace `jsonschema` validation in `EndpointLoader` with Pydantic models (`ToolDefinitionModel`, `PromptDefinitionModel`, etc.).
   - These models should encapsulate enabled/disabled logic, URI/name validation, and cross-reference checks. Consider using `RootModel[List[ToolDefinitionModel]]` for directory scanning utilities.
2. **Prompts / resources / evals**
   - Repeat the pattern for each schema-heavy component, unifying shared blocks (e.g., `AuditConfigModel`, `LLMModelConfigModel`) to reduce duplication.
3. **Schema export**
   - If we still need JSON artifacts for external tooling, generate them from the Pydantic models during packaging (e.g., via a build step that writes to `dist/schemas/`).
4. **Testing**
   - Add targeted tests for each loader that ensure invalid definitions trigger `ValidationError` with helpful messages, and that derived defaults (enabled flags, templated names) behave as expected.

Exit criteria: All schema validations in `mxcp/server/schemas/` are backed by Pydantic models, and `jsonschema` is no longer required in runtime dependencies.

---

## Phase 4 – Final Cleanup & Enforcement
1. **Remove legacy artifacts**
   - Delete remaining JSON schema files and any helper utilities that existed solely for `jsonschema`.
   - Drop `types-jsonschema` stubs and related dev dependencies if unused elsewhere.
2. **Static analysis**
   - Enable mypy/pyright rules (or custom scripts) to flag residual `.get()`/`dict[...]` usage on config objects, ensuring future code sticks to typed models.
3. **Documentation**
   - Update user-facing docs (e.g., `docs/guides/configuration.md`) to reference the new schema definitions or the auto-generated JSON schema exports.
4. **Performance & regression review**
   - Profile configuration loading to ensure Pydantic validation doesn’t introduce noticeable latency.
   - Confirm CLI commands and server startups produce identical behavior and logs.

Exit criteria: All configs/definitions rely on Pydantic, legacy schemas are gone (or auto-generated), type checking enforces model usage, and jsonschema dependency is fully removed.

---

## Risk Mitigation & Tooling
- **Gradual rollout**: Each phase should ship behind internal feature flags or environment toggles to allow canary testing.
- **Telemetry**: Add temporary counters/logging to measure how often dict fallbacks are used during the bridge period.
- **Backwards compatibility**: Because configs are local files, ensure we support `model_validate` with clear errors that match (or improve upon) current jsonschema messages.
- **Contributor guidance**: Add a short section to `docs/guides/configuration.md` explaining how to add fields to the models, including where defaults/validators live.

---

## Tracking
Create one epic per phase with child tasks for:
- Model definition + validators
- Loader updates
- Consumer migrations (grouped by package)
- Test coverage
- Schema removal / dependency cleanup

Progress through the phases only after the previous phase meets its exit criteria to avoid overlapping risk areas. This ensures we maintain a fully typed, immutable configuration surface before tackling downstream definitions.

