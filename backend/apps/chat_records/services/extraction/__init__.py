"""录制/视频提取模块：抽帧、去重、录制管理。"""

from .extract_helpers import DedupState, ExtractParams
from .frame_processing_service import FrameProcessingService
from .frame_selection_service import FrameSelectionService
from .recording_extract_facade import RecordingExtractFacade, RecordingExtractParams
from .recording_service import RecordingService
from .video_frame_extract_service import FFProbeInfo, VideoFrameExtractService

__all__ = [
    "DedupState",
    "ExtractParams",
    "FFProbeInfo",
    "FrameProcessingService",
    "FrameSelectionService",
    "RecordingExtractFacade",
    "RecordingExtractParams",
    "RecordingService",
    "VideoFrameExtractService",
]
