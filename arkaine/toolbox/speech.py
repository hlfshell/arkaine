import os
from os import path
from threading import Lock
from typing import Dict, Optional
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
        if id is None:
            id = uuid4()

        if api_key is None:
            api_key = os.getenv("OPENAI_API_KEY")
        self.__client = OpenAI(api_key=api_key)

        allowed_formats = ["mp3", "opus", "aac", "flac", "wav", "pcm"]
        if format not in allowed_formats:
            raise ValueError(
                f"Invalid format: {format}; mus be one of {allowed_formats}"
            )
        self.__format = format

        self.__model = model

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
            if voice not in self.VOICES:
                raise ValueError(
                    f"Invalid voice: {voice}; must be one of {self.VOICES}"
                )
            self.__voice = voice

        if instructions is None:
            arguments.append(
                Argument(
                    name="instructions",
                    type="str",
                    description=(
                        "Additional instructions for the output, such as how "
                        "to pronounce certain words, the flow of the speech, "
                        "or the emotion to impart"
                    ),
                    required=False,
                    default="",
                )
            )
            self.__instructions = None
        else:
            self.__instructions = instructions

        self.__working_directory = working_directory

        super().__init__(
            name=name,
            args=arguments,
            examples=[],
            description=(
                "Converts a given text into an audio file of content spoken."
            ),
            func=self._speak,
            result=Result(
                type="SpeechAudio",
                description="The audio output of the text-to-speech model",
            ),
            id=id,
        )

    def _speak(
        self, context: Context, text: str, *args, **kwargs
    ) -> SpeechAudio:
        # Pull out voice and instructions, whether from the forcibly set body or from
        # the aruments within
        voice = ""
        if self.__voice is None:
            voice = kwargs.get("voice", None)
            if voice is None and len(args) > 0:
                voice = args.pop(0)
        else:
            voice = self.__voice

        if voice not in self.VOICES:
            raise ValueError(
                f"Invalid voice: {voice}; must be one of {self.VOICES}"
            )

        instructions = ""
        if self.__instructions is None:
            instructions = kwargs.get("instructions", None)
            if instructions is None and len(args) > 1:
                instructions = args.pop(1)
        else:
            instructions = self.__instructions

        if voice is None:
            raise ValueError("Voice is required")

        response = self.__client.audio.speech.create(
            model=self.__model,
            voice=voice,
            input=text,
            instructions=instructions,
            # format=self.__format,
        )

        if self.__working_directory is not None:
            filepath = path.join(
                self.__working_directory, f"{uuid4()}.{self.__format}"
            )
        else:
            filepath = path.join(
                SpeechAudioOptions.get_instance().working_directory,
                f"{uuid4()}.{self.__format}",
            )

        response.stream_to_file(filepath)

        return SpeechAudio(
            file_path=filepath,
            extension=self.__format,
        )
