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


class RegionSource(str, enum.Enum):
    """How a tile-tessellation request specifies the sky region to cover."""

    CONE = "cone"
    PROJECT_FOOTPRINT = "project_footprint"
    BOUNDING_BOX = "bounding_box"
