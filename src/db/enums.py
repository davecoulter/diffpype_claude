import enum


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROCESS = "in_process"
    COMPLETE = "complete"
    FAILED = "failed"


class CeleryQueue(str, enum.Enum):
    LIGHT = "light"
    HEAVY_MEMORY = "heavy_memory"
    GPU = "gpu"
