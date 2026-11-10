# Incident Log – Building Plan Compliance Pre-Check

| Incident | Cause / Observation | Resolution / Action |
|---|---|---|
| Missing `fakeredis` during test collection | Test dependency was not installed in the virtual environment. | Install `fakeredis` and include it in project dependencies. |
| ChromaDB installation/build issue on Windows | Native build dependencies were unavailable in the original Python environment. | Use a compatible Python 3.11 virtual environment and required build tools. |
| ChromaDB telemetry warning | Telemetry warning appeared during retrieval initialization. | Retrieval functionality was verified; warning did not prevent retrieval. |
| Three evaluation tests failed | Tests reported `FileNotFoundError` for an expected evaluation scenario file. | Requires path investigation and correction. |
| Redis unavailable behaviour | Rate limiter catches Redis errors and allows requests to continue. | Documented as fail-open behaviour; monitor Redis availability. |
| TruLens judge evaluation unavailable | Project currently uses a stub LLM provider without a configured judge model. | Keep deterministic evaluation and defer judge-based metrics until a real provider is configured. |

## Notes

- Do not commit `.venv311/`, `chroma_db/`, `__pycache__/`, API keys, or other generated/local files.
- Record future incidents with their date, observed behaviour, cause, and resolution.
- Do not report unverified evaluation metrics as successful results.