"""
Generate an audio file that reads a text file aloud at a precise words-per-minute
rate, using Microsoft's text-to-speech voices.

How it works:
    edge-tts's streaming API returns, alongside the audio itself, WordBoundary
    events describing the exact start time and duration of every word as it was
    spoken in one continuous, naturally-paced synthesis pass. This script:

      1. Synthesizes the entire input text in a single streaming call.
      2. Uses the WordBoundary events to slice each individual word's audio out
         of that one continuous recording.
      3. Computes exactly how much silence needs to sit between words so the
         average rate across the whole file equals the target wpm.
      4. Reassembles the word slices with calculated silence gaps in between.

Requirements:
    pip install edge-tts pydub
    ffmpeg must be installed and on your PATH (pydub uses it):
      macOS:   brew install ffmpeg
      Ubuntu:  sudo apt install ffmpeg
      Windows: https://ffmpeg.org/download.html

    edge-tts requires an internet connection at runtime (it calls Microsoft's
    TTS service). It's free and doesn't require an API key.

Usage:
    python3 dictate_wpm.py input.txt --wpm 10 -o output.mp3
    python3 dictate_wpm.py input.txt --wpm 10 --voice en-US-GuyNeural -o output.mp3

    To list all available voices:
        edge-tts --list-voices

Options:
    --wpm         Target average words-per-minute for the whole file (required)
    --voice       edge-tts voice name (default: en-US-MichelleNeural)
    --rate        Speaking rate adjustment for the synthesized speech overall,
                  as a percentage string, e.g. "-10%" or "+15%" (default: "+0%").
                  Use this to make the underlying speech itself slower/faster;
                  the script still controls final WPM precisely via silence gaps.
    -o / --output Output audio file path (default: output.mp3)

Notes:
    WordBoundary timing is provided by edge-tts's (unofficial, reverse-engineered)
    API and its exact granularity can vary slightly by voice/language. In the rare
    case a word has zero measured duration, a small minimum floor is applied so it
    isn't silently dropped from the output.
"""

import argparse
import asyncio
import io
import re
import shutil
import sys
from pathlib import Path

try:
    import edge_tts
except ImportError:
    sys.exit("Error: edge-tts not installed. Run: pip install edge-tts")

try:
    from pydub import AudioSegment
except ImportError:
    sys.exit("Error: pydub not installed. Run: pip install pydub")


TICKS_PER_MS = 10_000  # edge-tts WordBoundary offsets/durations are in 100-ns ticks
MIN_WORD_MS = 40        # floor so a mismeasured word doesn't vanish entirely


def check_ffmpeg_available():
    if shutil.which("ffmpeg") is None:
        sys.exit(
            "Error: ffmpeg not found on PATH (required by pydub).\n"
            "Install it first:\n"
            "  macOS:   brew install ffmpeg\n"
            "  Ubuntu:  sudo apt install ffmpeg\n"
            "  Windows: https://ffmpeg.org/download.html"
        )

# Insert periods after each word (e.g. "Hello my" -> "Hello. my.")
def add_periods_after_words(s: str) -> str:
    def _replace(m):
        token = m.group(0)
        # If the token already ends with punctuation, leave it alone.
        if re.search(r'[.?!;:,]$', token):
            return token
        return token + '.'
    return re.sub(r"\S+", _replace, s)

async def synthesize_with_boundaries(text, voice, rate):
    """
    Single streaming call to edge-tts. Returns (audio_bytes, boundaries),
    where boundaries is a list of dicts: {"text": str, "start_ms": float, "dur_ms": float}
    in the order the words were spoken.
    """
    communicate = edge_tts.Communicate(add_periods_after_words(text), voice=voice, rate=rate, boundary="WordBoundary")
    audio_chunks = []
    boundaries = []

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            boundaries.append({
                "text": chunk["text"],
                "start_ms": chunk["offset"] / TICKS_PER_MS,
                "dur_ms": chunk["duration"] / TICKS_PER_MS,
            })

    return b"".join(audio_chunks), boundaries

def main():
    parser = argparse.ArgumentParser(description="Generate natural-voice dictation audio at a precise WPM (single TTS call).")
    parser.add_argument("input_file", type=Path, help="Path to input text file")
    parser.add_argument("--wpm", type=float, required=True, help="Target average words per minute")
    parser.add_argument("--voice", default="en-US-MichelleNeural", help="edge-tts voice (default: en-US-MichelleNeural)")
    parser.add_argument("--rate", default="+0%",
                         help='Overall speaking rate adjustment, e.g. "-10%%" or "+15%%" (default: "+0%%")')
    parser.add_argument("-o", "--output", type=Path, default=Path("output.mp3"),
                         help="Output audio file (default: output.mp3)")
    args = parser.parse_args()

    check_ffmpeg_available()

    text = args.input_file.read_text(encoding="utf-8")

    if not re.search(r"\S", text):
        sys.exit("Error: input file contains no words.")

    print(f"Synthesizing text with voice '{args.voice}'...")
    audio_bytes, boundaries = asyncio.run(synthesize_with_boundaries(text, args.voice, args.rate))

    if not boundaries:
        sys.exit(
            "Error: no WordBoundary events were returned by edge-tts for this input.\n"
            "This can happen with some voices/languages, or with older edge-tts versions "
            "that don't accept the boundary= argument. Try `pip install --upgrade edge-tts` "
            "or a different --voice."
        )

    word_count = len(boundaries)
    target_total_seconds = (word_count / args.wpm) * 60.0

    print(f"Words: {word_count}")
    print(f"Target rate: {args.wpm} WPM  ->  target duration: {target_total_seconds:.1f}s")

    full_audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")

    # Slice each word's audio out of the single continuous recording.
    word_clips = []
    total_speech_ms = 0
    for b in boundaries:
        start_ms = max(0, int(round(b["start_ms"])))
        dur_ms = max(MIN_WORD_MS, int(round(b["dur_ms"])))
        end_ms = min(len(full_audio), start_ms + dur_ms)
        clip = full_audio[start_ms:end_ms]
        word_clips.append(clip)
        total_speech_ms += len(clip)

    total_speech_seconds = total_speech_ms / 1000.0
    silence_seconds_total = target_total_seconds - total_speech_seconds

    if silence_seconds_total < 0:
        sys.exit(
            f"Error: target WPM ({args.wpm}) is faster than natural speech allows here "
            f"(words alone take {total_speech_seconds:.1f}s, target was {target_total_seconds:.1f}s).\n"
            f"Try a higher --wpm, or speed up speech with e.g. --rate \"+20%%\"."
        )

    gap_ms = int(round((silence_seconds_total * 1000) / word_count))
    silence = AudioSegment.silent(duration=gap_ms)

    print(f"Speech-only duration: {total_speech_seconds:.1f}s. Adding {gap_ms}ms of silence after each word.")

    final_audio = AudioSegment.empty()
    for clip in word_clips:
        final_audio += clip + silence

    export_format = args.output.suffix.lstrip(".") or "mp3"
    final_audio.export(str(args.output), format=export_format)

    print(f"Done. Wrote {args.output}")


if __name__ == "__main__":
    main()
