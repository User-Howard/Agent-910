"""Join a voice channel and record the meeting as one mixed audio file.

Each speaker's decoded audio is written to their own WAV file, padded with
silence up front so every file starts at the same wall-clock instant, and a
`SilenceGeneratorSink` keeps filling gaps while someone's mic is idle. That
keeps all the per-speaker files aligned, so ffmpeg's `amix` can overlay them
into a single track afterwards without any manual offset math.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path

import discord
from discord.ext import voice_recv
from discord.ext.voice_recv import router as _voice_recv_router

_log = logging.getLogger(__name__)


def _resilient_packet_router_do_run(self: _voice_recv_router.PacketRouter) -> None:
    """Drop a single bad packet instead of killing listening for the whole channel.

    With Discord's now-mandatory E2EE (DAVE), the first packet or two from a
    speaker often can't be decrypted yet — the SSRC isn't mapped to a user, or
    the DAVE session isn't fully established — so opus decode raises OpusError
    for those. Upstream's PacketRouter.run() lets that exception escape
    _do_run() entirely, and its `finally` block then calls
    `voice_client.stop_listening()`, which silently ends capture for every
    speaker after just the first bad frame (github.com/imayhaveborkedit/
    discord-ext-voice-recv PacketRouter.run/_do_run). We only want to skip
    that one frame and keep listening.
    """
    while not self._end_thread.is_set():
        self.waiter.wait()
        with self._lock:
            for decoder in self.waiter.items:
                try:
                    data = decoder.pop_data()
                except Exception:  # noqa: BLE001 — one bad packet must never kill the router thread
                    _log.debug("Dropping undecodable packet for ssrc %s", decoder.ssrc, exc_info=True)
                    continue
                if data is not None:
                    self.sink.write(data.source, data)


_voice_recv_router.PacketRouter._do_run = _resilient_packet_router_do_run

_DECODER = voice_recv.sinks.OpusDecoder
CHANNELS = _DECODER.CHANNELS
SAMPLE_WIDTH = _DECODER.SAMPLE_SIZE // _DECODER.CHANNELS
SAMPLING_RATE = _DECODER.SAMPLING_RATE
_FRAME_ALIGN = SAMPLE_WIDTH * CHANNELS


class RecordingError(Exception):
    """A user-facing recording problem (already recording, nothing captured, etc.)."""


class _PerSpeakerWriter(voice_recv.AudioSink):
    """Writes each speaker's PCM to its own WAV file, time-aligned to session start."""

    def __init__(self, directory: Path):
        super().__init__()
        self._directory = directory
        self._started_at = time.perf_counter()
        self._lock = threading.Lock()
        self._writers: dict[int, wave.Wave_write] = {}
        self._names: dict[int, str] = {}
        self._closed = threading.Event()

    def wants_opus(self) -> bool:
        return False

    def write(self, user, data) -> None:
        key = user.id if user is not None else data.packet.ssrc
        with self._lock:
            writer = self._writers.get(key)
            if writer is None:
                path = self._directory / f"{key}.wav"
                writer = wave.open(str(path), "wb")  # noqa: SIM115 — stays open across writes, closed in cleanup()
                writer.setnchannels(CHANNELS)
                writer.setsampwidth(SAMPLE_WIDTH)
                writer.setframerate(SAMPLING_RATE)

                elapsed = time.perf_counter() - self._started_at
                silence_bytes = int(elapsed * SAMPLING_RATE) * _FRAME_ALIGN
                writer.writeframes(b"\0" * silence_bytes)

                self._writers[key] = writer
                self._names[key] = user.display_name if user is not None else f"Unknown speaker {key}"
            writer.writeframes(data.pcm)

    def cleanup(self) -> None:
        # Called by the reader's teardown thread when listening stops, and
        # defensively again from stop_recording() — safe either way, since
        # wave.Wave_write.close() is a no-op once the file is already closed.
        with self._lock:
            for writer in self._writers.values():
                writer.close()
        self._closed.set()

    async def wait_closed(self, timeout: float = 5.0) -> None:
        """Block until cleanup() has run, so files are fully flushed before reading them."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._closed.wait, timeout)

    @property
    def speakers(self) -> list[tuple[str, Path]]:
        """Each speaker's display name and their individual (pre-mix) WAV file."""
        return [(self._names[key], self._directory / f"{key}.wav") for key in self._writers]


@dataclass
class RecordingSession:
    voice_client: voice_recv.VoiceRecvClient
    directory: Path
    sink: _PerSpeakerWriter
    started_by: str


@dataclass
class MeetingRecording:
    mixed_audio: Path
    """The full meeting, all speakers combined into one track."""

    speakers: list[tuple[str, Path]]
    """Each speaker's display name and their individual (pre-mix) WAV file —
    useful for transcribing per-speaker instead of the mixed track. Deleted
    along with `mixed_audio.parent` once the caller is done with them."""


_sessions: dict[int, RecordingSession] = {}


async def start_recording(channel: discord.VoiceChannel, *, started_by: str) -> RecordingSession:
    """Join `channel` and start recording. Raises RecordingError if already recording here."""
    if channel.guild.id in _sessions:
        raise RecordingError("Already recording a meeting in this server — run `/stop` first.")

    directory = Path(tempfile.mkdtemp(prefix="agent910-rec-"))
    try:
        vc = await channel.connect(cls=voice_recv.VoiceRecvClient, self_deaf=False)
    except Exception as e:
        shutil.rmtree(directory, ignore_errors=True)
        raise RecordingError(f"Couldn't join {channel.mention}: {e}") from e

    sink = _PerSpeakerWriter(directory)
    vc.listen(voice_recv.SilenceGeneratorSink(sink))

    session = RecordingSession(voice_client=vc, directory=directory, sink=sink, started_by=started_by)
    _sessions[channel.guild.id] = session
    return session


async def stop_recording(guild_id: int) -> MeetingRecording | None:
    """Stop the recording for a guild and return the mixed audio + per-speaker files.

    Returns None if nobody's audio was actually captured. Raises RecordingError
    if there's no active recording, or if mixing the audio fails.
    """
    session = _sessions.pop(guild_id, None)
    if session is None:
        raise RecordingError("There's no recording in progress in this server.")

    # stop_listening() tears the reader down (incl. calling sink.cleanup()) on a
    # background thread, not synchronously — wait for it so we never read a WAV
    # file before its header is finalized. cleanup() is called again defensively
    # in case that teardown is still in flight after the timeout.
    session.voice_client.stop_listening()
    await session.sink.wait_closed()
    session.sink.cleanup()
    await session.voice_client.disconnect(force=False)

    speakers = session.sink.speakers
    if not speakers:
        shutil.rmtree(session.directory, ignore_errors=True)
        return None

    output = session.directory / "meeting.mp3"
    try:
        await _mix_to_mp3([path for _, path in speakers], output)
    except Exception:
        shutil.rmtree(session.directory, ignore_errors=True)
        raise
    return MeetingRecording(mixed_audio=output, speakers=speakers)


async def _mix_to_mp3(speaker_files: list[Path], output: Path) -> None:
    inputs: list[str] = []
    for path in speaker_files:
        inputs += ["-i", str(path)]

    filter_complex = f"amix=inputs={len(speaker_files)}:duration=longest:normalize=0"
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-y",
        *inputs,
        "-filter_complex",
        filter_complex,
        "-c:a",
        "libmp3lame",
        "-q:a",
        "4",
        str(output),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RecordingError(
            "Mixing the recorded audio failed (ffmpeg error): "
            f"{stderr.decode(errors='replace')[-500:]}"
        )
