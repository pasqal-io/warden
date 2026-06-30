# QPU Mock API

Mock version of the QPU API for for development/testing purposes.

Eventually using this mock api for e2e tests and resilience to failures of QPU by
using this mock for chaos engineering.

## Scope

### Mocked endpoints

Only the following endpoints are mocked (for Warden compatibility):

- `POST /jobs`
- `GET /jobs/<ID>`
- `PUT /jobs/cancel`
- `GET /programs/<ID>`
- `GET /system`
- `GET /system/operational`

### Behavior

Only handles nominal behavior for Warden compatibility, meaning:

- Return FC1 QPU properties
- QPU always UP
- Job creation always OK
- 1st job status GET request returns "RUNNING"
- 2nd job status request returns "DONE" with mock results

### Timed job behavior

If we set the env variable `MOCK_QPU_API_IS_TIMED`, we can set the mock API to simulate a job runtime that depends on the number of shots requested in the job. 

We can pass the duration in seconds of a single shot in the `MOCK_QPU_API_SHOT_DURATION_S` env var. If it is not set, the default is `0.01s`.

Hence a job with 500 shots will take `500 x 0.01 = 5s` after the first `GET` request before it returns as `DONE`.

## Run

From the base of the Warden repo:

```bash
make start-qpu-mock
# Or with auto reload when modifying API
make start-qpu-mock-dev
```

## Next steps

- Mock error response
- Add option to control error scenarios for API to be used in E2E test

