import os
from abc import abstractmethod
from os import path
from threading import Lock
from typing import Dict, List, Optional
from uuid import uuid4

from openai import OpenAI

from arkaine.tools.abstract import AbstractTool
from arkaine.tools.argument import Argument
from arkaine.tools.context import Context
from arkaine.tools.result import Result


class SpeechAudioOptions:

    __instance = None
    _lock = Lock()
    __options = {
        "working_directory": path.join(
            path.abspath(path.curdir), "speech_audio_files"
        ),
    }

    @classmethod
    def get_instance(cls):
        if cls.__instance is None:
            with cls._lock:
                if cls.__instance is None:
                    cls.__instance = cls()
        return cls.__instance

    @property
    def working_directory(self) -> str:
        with self._lock:
            dir = self.__options["working_directory"]
            if not path.exists(dir):
                os.makedirs(dir)
            return dir

    @working_directory.setter
    def working_directory(self, value: str):
        with self._lock:
            if not path.exists(value):
                os.makedirs(value)
            self.__options["working_directory"] = value


class SpeechAudio:

    def __init__(
        self,
        file_path: Optional[str] = None,
        data: Optional[bytes] = None,
        extension: Optional[str] = None,
    ):
        if file_path is None and data is None:
            raise ValueError("Either file_path or data must be provided")

        if file_path is not None:
            self.file_path = file_path
            self.__data = None
            if extension is not None:
                self.__extension = extension
            else:
                self.__extension = path.splitext(file_path)[1]
        else:
            if extension is None:
                extension = "mp3"
            self.__extension = extension
            self.file_path = path.join(
                SpeechAudioOptions.get_instance().working_directory,
                f"{uuid4()}.{self.__extension}",
            )
            self.__data = data

    def __str__(self):
        return f"Audio(file_path={self.file_path})"

    @property
    def data(self) -> bytes:
        if self.__data is None:
            with open(self.file_path, "rb") as f:
                self.__data = f.read()
        return self.__data

    def to_json(self) -> Dict[str, str]:
        return {
            "file_path": self.file_path,
        }

    @classmethod
    def from_json(cls, json: Dict[str, str]) -> "SpeechAudio":
        return cls(file_path=json["file_path"])


class TextToSpeechTool(AbstractTool):
    _rules = {
        "args": {
            "required": [
                Argument(
                    name="text", type="str", description="The text to speak"
                ),
            ],
            "allowed": [
                Argument(
                    name="voice",
                    type="str",
                    description="The name/id of the voice to use",
                ),
                Argument(
                    name="instructions",
                    type="str",
                    description=(
                        "Additional instructions for the output; support the "
                        "generation; varies across models"
                    ),
                ),
            ],
        },
        "result": {
            "required": ["SpeechAudio"],
        },
    }

    def __init__(
        self,
        name: str,
        voice: Optional[str] = None,
        instructions: Optional[str] = None,
        working_directory: Optional[str] = None,
        id: Optional[str] = None,
        description: str = "Converts a given text into an audio file of content spoken.",
        format: str = "mp3",
        cleanup_on_del: bool = True,
    ):
        if id is None:
            id = uuid4()

        self._working_directory = working_directory
        self._format = format

        arguments = [
            Argument(
                name="text",
                type="str",
                required=True,
                description="The text to speak",
            ),
        ]

        if voice is None:
            arguments.append(
                Argument(
                    name="voice",
                    type="str",
                    description="The name/id of the voice to use",
                    required=True,
                )
            )
            self.__voice = None
        else:
            if voice not in self.voices:
                raise ValueError(
                    f"Invalid voice: {voice}; must be one of {self.voices}"
                )
            self.__voice = voice

        if instructions is None:
            arguments.append(
                Argument(
                    name="instructions",
                    type="str",
                    description=(
                        "Additional instructions for the output; support the "
                        "generation; varies across models"
                    ),
                )
            )
            self._instructions = None
        else:
            self._instructions = instructions

        self.__cleanup_on_del = cleanup_on_del
        self.__files_tracker: List[str] = []

        super().__init__(
            name=name,
            args=arguments,
            examples=[],
            description=description,
            func=self._call_speak,
            result=Result(
                type="SpeechAudio",
                description="The audio output of the text-to-speech model",
            ),
            id=id,
        )

    def _call_speak(self, context: Context, *args, **kwargs) -> SpeechAudio:
        if "text" not in kwargs:
            if len(args) == 0:
                raise ValueError("text is required")
            text = args.pop(0)
        else:
            text = kwargs["text"]

        voice = ""
        if self.__voice is None:
            voice = kwargs.get("voice", None)
            if voice is None and len(args) > 0:
                voice = args.pop(0)
        else:
            voice = self.__voice

        if voice not in self.voices:
            raise ValueError(
                f"Invalid voice: {voice}; must be one of {self.list_voices}"
            )

        instructions = ""
        if self._instructions is None:
            instructions = kwargs.get("instructions", None)
            if instructions is None and len(args) > 0:
                instructions = args.pop(0)
        else:
            instructions = self._instructions

        speech = self.speak(context, text, voice, instructions)

        if self.__cleanup_on_del:
            self.__files_tracker.append(speech.file_path)

        return speech

    def __del__(self):
        if self.__cleanup_on_del:
            for file_path in self.__files_tracker:
                # If it exists, remove it
                if path.exists(file_path):
                    os.remove(file_path)

    @property
    @abstractmethod
    def voices(self) -> List[str]:
        raise NotImplementedError("Subclasses must implement list_voices")

    @abstractmethod
    def speak(
        self, context: Context, text: str, voice: str, instructions: str
    ) -> SpeechAudio:
        raise NotImplementedError("Subclasses must implement _speak")


class TextToSpeechOpenAI(TextToSpeechTool):

    VOICES = [
        "alloy",
        "ash",
        "ballad",
        "coral",
        "echo",
        "fable",
        "onyx",
        "nova",
        "sage",
        "shimmer",
    ]

    def __init__(
        self,
        model: Optional[str] = "gpt-4o-mini-tts",
        api_key: Optional[str] = None,
        format: Optional[str] = "mp3",
        voice: Optional[str] = None,
        instructions: Optional[str] = None,
        working_directory: Optional[str] = None,
        name: str = "text_to_speech",
        id: Optional[str] = None,
    ):
        if api_key is None:
            api_key = os.getenv("OPENAI_API_KEY")
        self.__client = OpenAI(api_key=api_key)

        allowed_formats = ["mp3", "opus", "aac", "flac", "wav", "pcm"]
        if format not in allowed_formats:
            raise ValueError(
                f"Invalid format: {format}; mus be one of {allowed_formats}"
            )

        self.__model = model

        super().__init__(
            name=name,
            voice=voice,
            instructions=instructions,
            working_directory=working_directory,
            id=id,
            format=format,
        )

    @property
    def voices(self) -> List[str]:
        return TextToSpeechOpenAI.VOICES

    def speak(
        self, context: Context, text: str, voice: str, instructions: str
    ) -> SpeechAudio:

        response = self.__client.audio.speech.create(
            model=self.__model,
            voice=voice,
            input=text,
            instructions=instructions,
        )

        if self._working_directory is not None:
            filepath = path.join(
                self._working_directory, f"{uuid4()}.{self._format}"
            )
        else:
            filepath = path.join(
                SpeechAudioOptions.get_instance().working_directory,
                f"{uuid4()}.{self._format}",
            )

        response.stream_to_file(filepath)

        return SpeechAudio(
            file_path=filepath,
            extension=self._format,
        )


class TextToSpeechKokoro(TextToSpeechTool):

    VOICES = [
        "af_alloy",
        "af_aoede",
        "af_bella",
        "af_heart",
        "af_jessica",
        "af_kore",
        "af_nicole",
        "af_nova",
        "af_river",
        "af_sarah",
        "af_sky",
        "am_adam",
        "am_echo",
        "am_eric",
        "am_fenrir",
        "am_liam",
        "am_michael",
        "am_onyx",
        "am_puck",
        "am_santa",
        "bf_alice",
        "bf_emma",
        "bf_isabella",
        "bf_lily",
        "bm_daniel",
        "bm_fable",
        "bm_george",
        "bm_lewis",
        "ff_siwis",
        "hf_alpha",
        "hf_beta",
        "hm_omega",
        "hm_psi",
    ]

    def __init__(
        self,
        lang_code: str = "a",
        voice: Optional[str] = None,
        speed: Optional[float] = 1.0,
        format: str = "wav",
        working_directory: Optional[str] = None,
        name: str = "text_to_speech",
        id: Optional[str] = None,
    ):
        try:
            from kokoro import KPipeline
        except ImportError:
            raise ImportError(
                "Kokoro is not installed. Please install it using `pip install kokoro==0.9.2`."
            )

        try:
            import soundfile as sf

            self.__sf = sf
        except ImportError:
            raise ImportError(
                "soundfile is not installed. Please install it using `pip install soundfile==0.13.1`."
            )

        self.__pipeline = KPipeline(lang_code=lang_code)
        self.__speed = speed

        super().__init__(
            name=name,
            voice=voice,
            instructions="",
            working_directory=working_directory,
            id=id,
            format=format,
        )

    @property
    def voices(self) -> List[str]:
        return TextToSpeechKokoro.VOICES

    def speak(
        self, context: Context, text: str, voice: str, instructions: str
    ) -> SpeechAudio:
        generator = self.__pipeline(
            text, voice=voice, speed=self.__speed, split_pattern=r"\n+"
        )

        # We'll only take the first generated audio segment
        for _, _, audio in generator:
            if self._working_directory is not None:
                filepath = path.join(
                    self._working_directory, f"{uuid4()}.{self._format}"
                )
            else:
                filepath = path.join(
                    SpeechAudioOptions.get_instance().working_directory,
                    f"{uuid4()}.{self._format}",
                )

            self.__sf.write(filepath, audio, 24000)

            return SpeechAudio(file_path=filepath, extension=self._format)


class TextToSpeechGoogle(TextToSpeechTool):
    GENDERS = {
        "NEUTRAL": "NEUTRAL",
        "MALE": "MALE",
        "FEMALE": "FEMALE",
    }

    def __init__(
        self,
        voice: Optional[str] = None,
        api_key: Optional[str] = None,
        credentials_path: Optional[str] = None,
        format: str = "mp3",
        working_directory: Optional[str] = None,
        name: str = "text_to_speech",
        id: Optional[str] = None,
    ):
        if api_key is None:
            api_key = os.getenv("GOOGLE_API_KEY")

        if credentials_path is None:
            credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

        if api_key is None and credentials_path is None:
            raise ValueError(
                "Either api_key or credentials_path must be provided or set "
                "via the environment variables GOOGLE_API_KEY or "
                "GOOGLE_APPLICATION_CREDENTIALS, respectively"
            )

        try:
            from google.cloud import texttospeech

            if credentials_path is not None:
                self.__client = (
                    texttospeech.TextToSpeechClient.from_service_account_json(
                        credentials_path
                    )
                )
            else:
                from google.api_core import client_options

                options = client_options.ClientOptions(api_key=api_key)
                self.__client = texttospeech.TextToSpeechClient(
                    client_options=options
                )
            self.__texttospeech = texttospeech
        except ImportError:
            raise ImportError(
                "Google Cloud Text-to-Speech is not installed. Please install it using "
                "`pip install google-cloud-texttospeech==2.25.1`"
            )

        self.__voices = {}
        response = self.__client.list_voices()
        for v in response.voices:
            self.__voices[v.name] = {
                "gender": v.ssml_gender,
                "rate": v.natural_sample_rate_hertz,
                "languages": v.language_codes,
            }

        # Set up audio encoding
        format_mapping = {
            "mp3": self.__texttospeech.AudioEncoding.MP3,
            "wav": self.__texttospeech.AudioEncoding.LINEAR16,
            "ogg": self.__texttospeech.AudioEncoding.OGG_OPUS,
        }
        if format not in format_mapping:
            raise ValueError(
                f"Invalid format: {format}; must be one of "
                f"{list(format_mapping.keys())}"
            )
        self.__audio_encoding = format_mapping[format]

        super().__init__(
            name=name,
            voice=voice,
            instructions="",
            working_directory=working_directory,
            id=id,
            format=format,
        )

    @property
    def voices(self) -> List[str]:
        return list(self.__voices.keys())

    def speak(
        self, context: Context, text: str, voice: str, instructions: str
    ) -> SpeechAudio:
        # Create synthesis input
        synthesis_input = self.__texttospeech.SynthesisInput(text=text)

        # Configure voice
        voice_options = self.__voices[voice]

        voice_params = self.__texttospeech.VoiceSelectionParams(
            language_code=voice_options["languages"][0],
            name=voice,
            ssml_gender=voice_options["gender"],
        )

        # Configure audio
        audio_config = self.__texttospeech.AudioConfig(
            audio_encoding=self.__audio_encoding
        )

        # Generate speech
        response = self.__client.synthesize_speech(
            input=synthesis_input, voice=voice_params, audio_config=audio_config
        )

        # Save the audio
        if self._working_directory is not None:
            filepath = path.join(
                self._working_directory, f"{uuid4()}.{self._format}"
            )
        else:
            filepath = path.join(
                SpeechAudioOptions.get_instance().working_directory,
                f"{uuid4()}.{self._format}",
            )

        with open(filepath, "wb") as f:
            f.write(response.audio_content)

        return SpeechAudio(
            file_path=filepath,
            extension=self._format,
        )
