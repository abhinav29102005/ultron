"""
speech/speech_to_text/stt_pipeline.py – Listen, then transcribe

The recorder's stream is opened per capture rather than held for the life of
the pipeline. Holding it meant this object owned the microphone permanently,
which starved the wake-word detector: it could never open the device, so
``run.py --mode wakeword`` span at 5 Hz printing "waiting for wake word" and
never heard one.
"""

from speech.speech_to_text.recorder import Recorder
from speech.speech_to_text.transcriber import Transcriber


class SpeechPipeline:

    def __init__(self):
        self.recorder = Recorder()
        self.transcriber = Transcriber()

    def listen(self):
        # Silence our own output first: the mic picks up the speakers, so
        # music playing would otherwise be recorded instead of the user.
        from speech.mic_guard import listening_quiet

        with listening_quiet():
            self.recorder.start()
            try:
                audio = self.recorder.listen()
            finally:
                # Released here so the wake-word detector can have the device
                # back while we transcribe.
                self.recorder.stop()

        if audio is None:
            return ""

        return self.transcriber.transcribe(audio)

    def stop(self):
        self.recorder.stop()
