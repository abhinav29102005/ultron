"""
This is where I would convert the speech received to text using faster-whisper
"""

from faster_whisper import WhisperModel
import numpy as np
from speech.speechconfig import (
    MODEL_NAME,
    DEVICE,
    COMPUTE_TYPE,
    BEAM_SIZE
)

class Transcriber:
    def __init__(self):
        self.model = WhisperModel(
            MODEL_NAME,
            device = DEVICE,
            compute_type= COMPUTE_TYPE
        )
    
    def transcribe(self, audio: np.ndarray) -> str:

        segments, info = self.model.transcribe(
            audio,
            beam_size=BEAM_SIZE
        )
        
        text = ""
        for segment in segments:
            text += segment.text + " "
        
        return text.strip() 
    
    def transcribe_file(self, file_path: str) -> str:

        segments,info = self.model.transcribe(
            file_path,
            beam_size = BEAM_SIZE
        )
        
        text = ""
        for segment in segments:
            text += segment.text + " "
        
        return text.strip() 