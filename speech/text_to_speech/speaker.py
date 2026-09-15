from piper import PiperVoice

from speech.speechconfig import (
    TTS_MODEL_PATH,
    TTS_DEVICE,
)


class Speaker:
    def __init__(self):
        self.voice = self.load_model()

    def load_model(self):
        """
        Load the Piper voice model.
        """

        return PiperVoice.load(
            model_path=TTS_MODEL_PATH,
            use_cuda=(TTS_DEVICE == "cuda")
        )

    def generate(self, text: str):
        """
        Yield one AudioChunk at a time.
        """

        yield from self.voice.synthesize(text)