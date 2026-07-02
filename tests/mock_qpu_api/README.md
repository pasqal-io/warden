# QPU Mock API

Mock version of the QPU API for for development/testing purposes.

Eventually using this mock api for e2e tests and resilience to failures of QPU by
using this mock for chaos engineering.

## Scope

### Mocked endpoints

Only the following endpoints are mocked (for Warden compatibility):

- `POST /jobs`
- `GET /jobs/<ID>`
- `PUT /jobs/cancel`
- `GET /system`
- `GET /system/operational`

### Behavior

Only handles nominal behavior for Warden compatibility, meaning:

- Return FC1 QPU properties
- QPU always UP
- Job creation always OK
- 1st job status GET request returns "RUNNING" and effectively starts the job
- Job status request returns "DONE" after `MOCK_QPU_API_SHOT_DURATION_S x N_SHOTS` seconds
    - With mocked results
    - Qutip-emulated results if `MOCK_QPU_API_EMUL` is set
        - Returns "ERROR" status with the emulation went wrong

## Run

From the base of the Warden repo:

```bash
make start-qpu-mock
# Or with auto reload when modifying API
make start-qpu-mock-dev
```

## Configuration

The mock qpu API is configured through environment variables

| Variable          | Description       | Default           | Required          | Example Value     |
|-------------------|-------------------|-------------------|-------------------|-------------------|
| `MOCK_QPU_API_SHOT_DURATION_S`          | Simulated duration of a job shot       | `0.01`           | No          | `0.05`     |
| `MOCK_QPU_API_EMUL`          | Whether the mock API should return mocked values or results from a Qutip emulation. Set to a non empty value to enable emulation       | No           | No          | Any     |

## Next steps

- Mock error response
- Add option to control error scenarios for API to be used in E2E test

