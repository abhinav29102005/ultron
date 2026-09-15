"""
This is where I will handle the VAD logic which helps to detect when speech input is there and when it is not
"""
import torch
from silero_vad import (
    load_silero_vad,
    get_speech_timestamps
)
from speech.speechconfig import VAD_SAMPLE_RATE
class VAD:
    def __init__(self):
        self.model = load_silero_vad()

    def has_speech(self, audio):
        if not isinstance(audio, torch.Tensor):
            audio = torch.from_numpy(audio)
        speech = get_speech_timestamps(
            audio,
            self.model,
            sampling_rate=VAD_SAMPLE_RATE
        )
        return len(speech) > 0