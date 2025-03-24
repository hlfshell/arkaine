from __future__ import annotations

import io
import json
import os
from abc import ABC, abstractmethod
from os import path
from threading import Lock
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from openai import OpenAI

from arkaine.tools.argument import Argument
from arkaine.tools.context import Context
from arkaine.tools.result import Result
from arkaine.tools.tool import Tool


# SpeechAudioOptions: Singleton class for managing speech audio file storage
# settings
#
# This class provides a centralized way to manage the working directory where
# speech audio files are stored. It uses a singleton pattern to ensure only one
# instance exists across the application.
#
# Properties:
#   working_directory (str): Get/set the directory path for storing audio files
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


# SpeechAudio: Class for handling speech audio file operations
#
# This class manages audio file data and operations, supporting both file-based
# and in-memory audio data handling.
#
# Args:
#   filepath (Optional[str]): Path to an existing audio file
#   data (Optional[bytes]): Raw audio data in bytes
#   format (Optional[str]): File extension (defaults to 'mp3')
#   text (Optional[str]): Text associated with the audio
class SpeechAudio:

    FORMATS = ["mp3", "wav", "ogg", "flac", "pcm"]

    def __init__(
        self,
        filepath: Optional[str] = None,
        data: Optional[bytes] = None,
        format: Optional[str] = None,
        text: Optional[str] = None,
    ):
        if filepath is None and data is None:
            raise ValueError("Either filepath or data must be provided")

        self.__text = text

        if filepath is not None:
            self.filepath = filepath
            self.__data = None
            if format is not None:
                self.__format = format.lower()
            else:
                self.__format = (
                    path.splitext(filepath)[1].lower().removeprefix(".")
                )
        else:
            if format is None:
                format = "mp3"
            if format.lower() not in SpeechAudio.FORMATS:
                raise ValueError(
                    f"Invalid format: {format}; must be one of "
                    f"{SpeechAudio.FORMATS}"
                )
            self.__format = format.lower()
            self.filepath = path.join(
                SpeechAudioOptions.get_instance().working_directory,
                f"{uuid4()}.{format}",  # do not use lowercase'd format here
            )
            self.__data = data

            self.save()

    @classmethod
    def _json_filepath(cls, filepath: str) -> str:
        return path.splitext(filepath)[0] + ".json"

    def __str__(self):
        return f"Audio(file_path={self.filepath})"

    def save(self):
        if self.__data is not None:
            with open(self.filepath, "wb") as f:
                f.write(self.__data)
            json_path = self._json_filepath(self.filepath)
            with open(json_path, "w") as f:
                json.dump(self.to_json(), f)

    @classmethod
    def load(cls, file_path: str) -> SpeechAudio:
        if not file_path.endswith(".json"):
            # Does it end with the format extension?
            ext = file_path.split(".")[0]
            if ext.lower() not in SpeechAudio.FORMATS:
                # In this situation, we will attempt to assume
                # that we were passed the filename without
                # an extension and will assume from here. If
                # this is not the case we will run into a file
                # not found error which is expected behavior.
                file_path = file_path + ".json"
            else:
                file_path = cls._json_filepath(file_path)

        with open(file_path, "r") as f:
            json_data = json.load(f)
        return cls(**json_data)

    @property
    def data(self) -> bytes:
        if self.__data is None:
            with open(self.filepath, "rb") as f:
                self.__data = f.read()
        return self.__data

    @property
    def file(self) -> io.FileIO:
        return open(self.filepath, "rb")

    @property
    def format(self) -> str:
        return self.__format

    @property
    def text(self) -> str:
        return self.__text

    @text.setter
    def text(self, value: str):
        self.__text = value

    def clear(self):
        """
        clear removes the audio data from memory
        """
        self.__data = None

    def to_json(self) -> Dict[str, str]:
        return {
            "file_path": self.filepath,
            "format": self.__format,
            "text": self.__text,
        }

    @classmethod
    def from_json(cls, json: Dict[str, str]) -> "SpeechAudio":
        return cls(
            file_path=json["file_path"],
            format=json["format"],
            text=json["text"],
        )


###############################################################################
# Text To Speech Tools
###############################################################################


# TextToSpeechTool: Abstract base class for text-to-speech implementations
#
# This class provides a common interface for different text-to-speech services.
# It handles argument processing and provides a standardized way to convert
# text to speech.
#
# Args:
#   name (str): Name of the tool
#   voice (Optional[str]): Default voice to use
#   working_directory (Optional[str]): Directory for storing audio files
#   id (Optional[str]): Unique identifier for the tool
#   description (str): Tool description
#   format (str): Audio format (default: 'mp3')
#   extra_arguments (List[Argument]): Additional arguments for the tool
class TextToSpeechTool(Tool, ABC):

    def __init__(
        self,
        name: str,
        voice: Optional[str] = None,
        working_directory: Optional[str] = None,
        id: Optional[str] = None,
        description: str = (
            "Converts a given text into an audio file of content spoken."
        ),
        format: str = "mp3",
        extra_arguments: List[Argument] = [],
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
            self.__voice = voice

        arguments.extend(extra_arguments)

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
        args: Dict[str, Any] = {}

        # Handle text argument first
        if "text" not in kwargs:
            if len(args) == 0:
                raise ValueError("text is required")
            args["text"] = args[0]
            args = args[1:]  # Shift remaining args
        else:
            args["text"] = kwargs["text"]

        # Handle voice argument
        args["voice"] = ""
        if self.__voice is None:
            if "voice" in kwargs:
                args["voice"] = kwargs["voice"]
            elif len(args) > 0:
                args["voice"] = args[0]
                args = args[1:]  # Shift remaining args
        else:
            args["voice"] = self.__voice

        # Handle remaining arguments
        for argument in self.args:
            if argument.name in ["text", "voice"]:  # Skip already handled args
                continue

            if argument.name in kwargs:
                args[argument.name] = kwargs[argument.name]
            elif argument.required:
                if len(args) > 0:
                    args[argument.name] = args[0]
                    args = args[1:]  # Shift remaining args
                else:
                    raise ValueError(f"{argument.name} is required")

        # Transfer any remaining kwargs
        args.update(kwargs)

        return self.speak(context, **args)

    @abstractmethod
    def speak(self, context: Context, text: str, voice: str) -> SpeechAudio:
        raise NotImplementedError("Subclasses must implement _speak")


# TextToSpeechOpenAI: OpenAI's text-to-speech implementation
#
# Implements text-to-speech using OpenAI's API with support for multiple voices
# and audio formats.
#
# Args:
#   model (Optional[str]): OpenAI model to use (default: 'gpt-4o-mini-tts')
#   api_key (Optional[str]): OpenAI API key
#   format (Optional[str]): Audio format ('mp3', 'opus', 'aac', 'flac',
#          'wav', 'pcm')
#   voice (Optional[str]): Default voice (must be one of VOICES)
#   instructions (Optional[str]): Additional TTS instructions
#   working_directory (Optional[str]): Output directory for audio files
#   name (str): Tool name
#   id (Optional[str]): Tool ID
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

        if voice is not None:
            if voice not in TextToSpeechOpenAI.VOICES:
                raise ValueError(
                    f"Invalid voice: {voice}; must be one of "
                    f"{TextToSpeechOpenAI.VOICES}"
                )

        if instructions is None:
            extra_arguments = [
                Argument(
                    name="instructions",
                    type="str",
                    description=(
                        "Additional instructions for the TTS model "
                        "on how to dictate or emote the text"
                    ),
                    required=False,
                ),
            ]
        else:
            extra_arguments = []

        super().__init__(
            name=name,
            voice=voice,
            working_directory=working_directory,
            id=id,
            format=format,
            extra_arguments=extra_arguments,
        )

    def speak(
        self,
        context: Context,
        text: str,
        voice: str,
        instructions: Optional[str] = None,
    ) -> SpeechAudio:
        if voice not in TextToSpeechOpenAI.VOICES:
            raise ValueError(
                f"Invalid voice: {voice}; must be one of "
                f"{TextToSpeechOpenAI.VOICES}"
            )

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
            filepath=filepath,
            format=self._format,
            text=text,
        )


# TextToSpeechKokoro: Kokoro-based text-to-speech implementation
#
# Implements text-to-speech using the Kokoro library, supporting multiple
# voices and speech speed adjustment.
#
# Args:
#   voice (Optional[str]): Default voice (must be one of VOICES)
#   speed (Optional[float]): Speech speed multiplier (default: 1.0)
#   working_directory (Optional[str]): Output directory for audio files
#   name (str): Tool name
#   id (Optional[str]): Tool ID
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
        voice: Optional[str] = None,
        speed: Optional[float] = 1.0,
        working_directory: Optional[str] = None,
        name: str = "text_to_speech",
        id: Optional[str] = None,
    ):
        try:
            from kokoro import KPipeline
        except ImportError:
            raise ImportError(
                "Kokoro is not installed. Please install it "
                "using `pip install kokoro==0.9.2`."
            )

        try:
            import soundfile as sf

            self.__sf = sf
        except ImportError:
            raise ImportError(
                "soundfile is not installed. Please install it "
                "using `pip install soundfile==0.13.1`."
            )

        if voice is not None and voice not in TextToSpeechKokoro.VOICES:
            raise ValueError(
                f"Invalid voice: {voice}; must be one of "
                f"{TextToSpeechKokoro.VOICES}"
            )

        self.__pipeline = KPipeline(lang_code="a")
        self.__speed = speed

        super().__init__(
            name=name,
            voice=voice,
            working_directory=working_directory,
            id=id,
            format="wav",
        )

    def speak(
        self,
        context: Context,
        text: str,
        voice: str,
    ) -> SpeechAudio:
        if voice not in TextToSpeechKokoro.VOICES:
            raise ValueError(
                f"Invalid voice: {voice}; must be one of "
                f"{TextToSpeechKokoro.VOICES}"
            )

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

            return SpeechAudio(
                filepath=filepath,
                format=self._format,
                text=text,
            )


# TextToSpeechGoogle: Google Cloud text-to-speech implementation
#
# Implements text-to-speech using Google Cloud TTS API, supporting multiple
# voices and audio formats.
#
# Args:
#   voice (Optional[str]): Default voice
#   api_key (Optional[str]): Google Cloud API key
#   credentials_path (Optional[str]): Path to Google Cloud credentials file
#   format (str): Audio format ('mp3', 'wav', 'ogg')
#   working_directory (Optional[str]): Output directory for audio files
#   name (str): Tool name
#   id (Optional[str]): Tool ID
class TextToSpeechGoogle(TextToSpeechTool):

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
                "Google Cloud Text-to-Speech is not installed. "
                "Please install it using "
                "`pip install google-cloud-texttospeech==2.25.1`"
            )

        self.voices = {}
        response = self.__client.list_voices()
        for v in response.voices:
            self.voices[v.name] = {
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
            working_directory=working_directory,
            id=id,
            format=format,
        )

    def speak(self, context: Context, text: str, voice: str) -> SpeechAudio:
        if voice not in self.voices:
            raise ValueError(
                f"Invalid voice: {voice}; must be one of "
                f"{list(self.voices.keys())}"
            )

        # Create synthesis input
        synthesis_input = self.__texttospeech.SynthesisInput(text=text)

        # Configure voice
        voice_options = self.voices[voice]

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

        return SpeechAudio(
            data=response.audio_content,
            format=self._format,
        )


# TextToSpeechElevenLabs: ElevenLabs text-to-speech implementation
#
# Implements text-to-speech using the ElevenLabs API, supporting multiple
# voices and models.
#
# Args:
#   voice (Optional[str]): Default voice ID
#   api_key (Optional[str]): ElevenLabs API key
#   model (Optional[str]): Model ID (default: 'eleven_multilingual_v2')
#   working_directory (Optional[str]): Output directory for audio files
#   name (str): Tool name
#   id (Optional[str]): Tool ID
class TextToSpeechElevenLabs(TextToSpeechTool):
    def __init__(
        self,
        voice: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = "eleven_multilingual_v2",
        working_directory: Optional[str] = None,
        name: str = "text_to_speech",
        id: Optional[str] = None,
    ):
        try:
            from elevenlabs import ElevenLabs
        except ImportError:
            raise ImportError(
                "ElevenLabs is not installed. Please install it using "
                "`pip install elevenlabs==1.54.0`"
            )

        self.__model = model
        if api_key is None:
            api_key = os.getenv("ELEVENLABS_API_KEY")
        if api_key is None:
            raise ValueError(
                "Either api_key or the environment variable "
                "ELEVENLABS_API_KEY must be provided"
            )
        self.__client = ElevenLabs(api_key=api_key)

        super().__init__(
            name=name,
            voice=voice,
            working_directory=working_directory,
            id=id,
        )

    def speak(self, context: Context, text: str, voice: str) -> SpeechAudio:

        response = self.__client.text_to_speech.convert(
            voice_id=voice,
            output_format="mp3_44100_128",
            text=text,
            model_id=self.__model,
        )

        # Collect all bytes from the generator
        audio_bytes = b"".join(response)

        return SpeechAudio(
            data=audio_bytes,
            format="mp3",
            text=text,
        )


###############################################################################
# Speech To Text Tools
###############################################################################


# SpeechToTextTool: Abstract base class for speech-to-text implementations
#
# This class provides a common interface for different speech-to-text services.
# It handles argument processing and provides a standardized way to convert
# audio to text.
#
# Args:
#   name (str): Name of the tool - defaults to "speech_to_text"
#   accepts (str): Input type ('speechaudio', 'filepath', or 'bytes'). This
#        changes what the tool will accept as an input. A SpeechAudio object,
#        a link to a filepath, or, for raw bytes either a set of bytes or an
#        io.BytesIO object.
#   returns (str): Return type either return just the text or a speechaudio
#        object (options are either 'text' or 'speechaudio')
#   allowed_formats (List[str]): List of supported audio formats
#   description (str): Tool description; has a default value
#   id (Optional[str]): Unique identifier for the tool
class SpeechToTextTool(Tool, ABC):

    FORMATS = SpeechAudio.FORMATS

    def __init__(
        self,
        name: str,
        accepts: str = "speechaudio",
        returns: str = "text",
        allowed_formats: List[str] = [],
        description: str = "Converts an audio file into text.",
        id: Optional[str] = None,
    ):
        args = []
        if accepts == "speechaudio":
            args.append(
                Argument(
                    name="audio",
                    description="The audio to convert to text.",
                    type="SpeechAudio",
                )
            )
        elif accepts == "filepath":
            args.append(
                Argument(
                    name="audio",
                    type="str",
                    description=(
                        "The path to the audio file to convert to text."
                    ),
                )
            )
        elif accepts == "bytes":
            args.append(
                Argument(
                    name="audio",
                    type="bytes",
                    description="The audio data to convert to text.",
                )
            )
        else:
            raise ValueError(
                "Invalid accepts: "
                f"{accepts}; must be one of "
                f"{['speechaudio', 'filepath', 'bytes']}"
            )
        self.__accepts = accepts

        if returns == "text":
            self._returns = "text"
            result = Result(
                type="str",
                description="The text converted from the audio.",
            )
        elif returns == "speechaudio":
            self._returns = "speechaudio"
            result = Result(
                type="SpeechAudio",
                description="The audio file converted to text.",
            )
        else:
            raise ValueError(
                "Invalid returns: {returns}; must be one of "
                f"{['text', 'speechaudio']}"
            )
        self.__returns = returns

        if len(allowed_formats) == 0:
            raise ValueError(
                "You must specify at least one format in allowed_formats; "
                f"acceptable formats are {SpeechToTextTool.FORMATS}"
            )
        if not all(f in SpeechToTextTool.FORMATS for f in allowed_formats):
            raise ValueError(
                "Invalid allowed_formats: "
                f"{allowed_formats}; must be a subset of "
                f"{SpeechToTextTool.FORMATS}"
            )
        self._allowed_formats = allowed_formats

        super().__init__(
            name=name,
            description=description,
            args=args,
            func=self.__call_transcribe,
            id=id,
            result=result,
        )

    def __call_transcribe(
        self,
        context: Context,
        audio: Union[
            SpeechAudio,
            str,
            bytes,
            io.IOBase,
            io.BufferedIOBase,
            io.RawIOBase,
        ],
    ) -> str:
        if self.__accepts == "bytes":
            if isinstance(
                audio,
                (io.IOBase, io.BufferedIOBase, io.RawIOBase, io.TextIOBase),
            ):
                data = audio.read()
                speech_audio = SpeechAudio(data=data)
            elif isinstance(audio, bytes):
                speech_audio = SpeechAudio(data=audio)
            else:
                raise ValueError(
                    "This speech to text tool only works with audio "
                    "data directly. Pass bytes directly or an io buffer"
                )
        elif self.__accepts == "filepath":
            speech_audio = SpeechAudio(filepath=audio)
        elif self.__accepts == "speechaudio":
            speech_audio = audio
        else:
            raise ValueError(
                "Invalid accepts: "
                f"{self.__accepts}; must be one of "
                f"{['speechaudio', 'filepath', 'bytes']}"
            )

        if speech_audio.format not in self._allowed_formats:
            raise ValueError(
                "Invalid format: "
                f"{speech_audio.format}; must be one of "
                f"{self._allowed_formats}"
            )

        result = self.transcribe(context, speech_audio)

        if self.__returns == "text":
            return result
        else:
            speech_audio.text = result
            return speech_audio

    @abstractmethod
    def transcribe(self, context: Context, audio: SpeechAudio) -> str:
        pass


# SpeechToTextOpenAI: OpenAI's speech-to-text implementation
#
# Implements speech-to-text using OpenAI's Whisper API with support for
# multiple audio formats.
#
# Args:
#   model (Optional[str]): OpenAI model to use (default: 'whisper-1')
#   api_key (Optional[str]): OpenAI API key (falls back to OPENAI_API_KEY env
#       var)
#   name (str): Tool name
#   accepts (str): Input type ('speechaudio', 'filepath', or 'bytes')
#   id (Optional[str]): Tool ID
#
# Supported formats: mp3, wav, ogg, flac
class SpeechToTextOpenAI(SpeechToTextTool):
    def __init__(
        self,
        model: Optional[str] = "whisper-1",
        api_key: Optional[str] = None,
        name: str = "speech_to_text",
        accepts: str = "filepath",
        id: Optional[str] = None,
    ):
        if api_key is None:
            api_key = os.getenv("OPENAI_API_KEY")
        if api_key is None:
            raise ValueError(
                "Either api_key or the environment variable "
                "OPENAI_API_KEY must be provided"
            )

        self.__client = OpenAI(api_key=api_key)
        self.__model = model

        super().__init__(
            name=name,
            accepts=accepts,
            returns="text",
            allowed_formats=[
                "mp3",
                "wav",
                "ogg",
                "flac",
            ],
            id=id,
        )

    def transcribe(self, context: Context, audio: SpeechAudio) -> str:
        with audio.file as f:
            response = self.__client.audio.transcriptions.create(
                model=self.__model,
                file=f,
            )
        return response.text


# SpeechToTextGoogle: Google Cloud speech-to-text implementation
#
# Implements speech-to-text using Google Cloud Speech-to-Text API with support
# for multiple audio formats and recognition models.
#
# Args:
#   model (Optional[str]): Google model to use (default: 'default')
#   api_key (Optional[str]): Google Cloud API key (falls back to
#       GOOGLE_API_KEY env var)
#   credentials_path (Optional[str]): Path to Google Cloud credentials file
#                    (falls back to GOOGLE_APPLICATION_CREDENTIALS env var)
#   name (str): Tool name
#   accepts (str): Input type ('speechaudio', 'filepath', or 'bytes')
#   id (Optional[str]): Tool ID
#
# Supported formats: mp3, wav, ogg, flac, pcm
class SpeechToTextGoogle(SpeechToTextTool):

    def __init__(
        self,
        model: Optional[str] = "default",
        api_key: Optional[str] = None,
        credentials_path: Optional[str] = None,
        name: str = "speech_to_text",
        accepts: str = "filepath",
        id: Optional[str] = None,
    ):
        if api_key is None:
            api_key = os.getenv("GOOGLE_API_KEY")

        if credentials_path is None:
            credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", None)

        if api_key is None and credentials_path is None:
            raise ValueError(
                "Either api_key or credentials_path must be provided or set "
                "via the environment variables GOOGLE_API_KEY or "
                "GOOGLE_APPLICATION_CREDENTIALS, respectively"
            )

        try:
            from google.cloud import speech

            if credentials_path is not None:
                self.__client = speech.SpeechClient.from_service_account_json(
                    credentials_path
                )
            else:
                from google.api_core import client_options

                options = client_options.ClientOptions(api_key=api_key)
                self.__client = speech.SpeechClient(client_options=options)

            self.__speech = speech
        except ImportError:
            raise ImportError(
                "Google Cloud Speech is not installed. "
                "Please install it using "
                "`pip install google-cloud-speech==2.31.1`"
            )

        self.__format_map = {
            "mp3": self.__speech.RecognitionConfig.AudioEncoding.MP3,
            "wav": self.__speech.RecognitionConfig.AudioEncoding.LINEAR16,
            "ogg": self.__speech.RecognitionConfig.AudioEncoding.OGG_OPUS,
            "flac": self.__speech.RecognitionConfig.AudioEncoding.FLAC,
            "pcm": self.__speech.RecognitionConfig.AudioEncoding.LINEAR16,
        }

        self.__model = model

        super().__init__(
            name=name,
            accepts=accepts,
            returns="text",
            allowed_formats=self.__format_map.keys(),
            id=id,
        )

    def transcribe(self, context: Context, audio: SpeechAudio) -> str:
        # Configure the audio source
        content = audio.data
        audio_source = self.__speech.RecognitionAudio(content=content)

        # Configure recognition settings
        config = self.__speech.RecognitionConfig(
            encoding=self.__format_map[audio.format],
            sample_rate_hertz=16000,  # Standard sample rate
            language_code="en-US",  # Default to English
            model=self.__model if self.__model != "default" else None,
        )

        # Perform the transcription
        response = self.__client.recognize(config=config, audio=audio_source)

        # Combine all transcription results
        transcript = ""
        for result in response.results:
            transcript += result.alternatives[0].transcript + " "

        return transcript.strip()


# SpeechToTextElevenLabs: ElevenLabs speech-to-text implementation
#
# Implements speech-to-text using the ElevenLabs API with support for
# multiple audio formats.
#
# Args:
#   api_key (Optional[str]): ElevenLabs API key (falls back to
#       ELEVENLABS_API_KEY env var)
#   name (str): Tool name
#   accepts (str): Input type ('speechaudio', 'filepath', or 'bytes')
#   id (Optional[str]): Tool ID
#
# Supported formats: mp3, wav, ogg, flac
class SpeechToTextElevenLabs(SpeechToTextTool):
    def __init__(
        self,
        api_key: Optional[str] = None,
        name: str = "speech_to_text",
        accepts: str = "filepath",
        id: Optional[str] = None,
    ):
        try:
            from elevenlabs import ElevenLabs
        except ImportError:
            raise ImportError(
                "ElevenLabs is not installed. Please install it using "
                "`pip install elevenlabs==1.54.0`"
            )

        if api_key is None:
            api_key = os.getenv("ELEVENLABS_API_KEY")
        if api_key is None:
            raise ValueError(
                "Either api_key or the environment variable "
                "ELEVENLABS_API_KEY must be provided"
            )

        self.__client = ElevenLabs(api_key=api_key)
        self.__model = "scribe_v1"  # Only one available for now

        super().__init__(
            name=name,
            accepts=accepts,
            returns="text",
            allowed_formats=["mp3", "wav", "ogg", "flac"],
            id=id,
        )

    def transcribe(self, context: Context, audio: SpeechAudio) -> str:
        response = self.__client.speech_to_text.convert(
            model_id=self.__model,
            file=audio.file,
        )

        # The response contains the transcribed text
        return response.text
