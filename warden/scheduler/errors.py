"""Custom exceptions for Scheduler"""


class QPUError(Exception):
    def __init__(self, *args):
        super().__init__(*args)


class QPUDownError(QPUError):
    def __init__(self, *args):
        super().__init__(*args)
