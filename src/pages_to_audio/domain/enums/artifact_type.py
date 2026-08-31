from enum import StrEnum


class ImageArtifactType(StrEnum):
    ORIGINAL = "original"
    DESKEW = "deskew"
    PERSPECTIVE = "perspective"
    CONTRAST = "contrast"
    DENOISE = "denoise"
    CROP = "crop"
    QUESTION_CROP = "question_crop"
    MEDIA_CROP = "media_crop"


class AudioArtifactType(StrEnum):
    STATUS = "status"
    FINAL = "final"
