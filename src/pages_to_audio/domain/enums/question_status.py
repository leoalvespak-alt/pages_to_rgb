from enum import StrEnum


class QuestionStatus(StrEnum):
    DISCOVERED = "DISCOVERED"
    INCOMPLETE = "INCOMPLETE"
    RESCUING = "RESCUING"
    READY = "READY"
    FAILED = "FAILED"
