# Building Proposal Data Contract

All requests to the pre-check service must be submitted as a JSON payload to the `POST /proposals` endpoint.

### Request Payload Schema
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `plot_area_sqm` | Float | `> 0` | Total plot area in square meters. |
| `road_width_m` | Float | `> 0` | Width of the abutting road in meters. |
| `proposed_height_m` | Float | `> 0` | Proposed building height in meters. |
| `building_use` | String | Allowed: `Residential`, `Commercial`, `Mixed-Use`, `Public/Semi-Public` | The intended use category of the building. |
| `notes` | String | Optional | Free-text description of the proposal. Passed to the agent for entity extraction and subject to prompt injection guardrails. |

### Response payload
Returns a 202 Accepted status with the following JSON structure:
- `run_id` (String): Unique identifier for the Redis queue task.
- `correlation_id` (String): Trace ID for observability.
- `status` (String): Always "queued" upon successful ingestion.
- `metrics` (Object): Contains ingestion timestamp.