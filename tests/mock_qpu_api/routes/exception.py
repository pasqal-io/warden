from mock_qpu_api.models.jobs import JobStatus


class JobCancelationError(Exception):
    def __init__(self, job_status: JobStatus):
        self.job_status = job_status
