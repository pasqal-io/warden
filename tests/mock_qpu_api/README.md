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

