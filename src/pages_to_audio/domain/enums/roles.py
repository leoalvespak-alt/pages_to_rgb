from enum import StrEnum


class AnswerRole(StrEnum):
    SOLVER = "solver"
    VERIFIER = "verifier"
    ARBITER = "arbiter"


class PageFrameRole(StrEnum):
    PRIMARY = "primary"
    ALTERNATE = "alternate"


class ActorType(StrEnum):
    ADMIN = "admin"
    GATEWAY = "gateway"
    SYSTEM = "system"
    WORKFLOW = "workflow"
