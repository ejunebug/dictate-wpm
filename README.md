# dictate_wpm

Generates an audio recording of a text file, read aloud at a precise
words-per-minute rate — including very slow rates (e.g. 10 WPM) that
standard text-to-speech speed controls can't produce cleanly.

Useful for building dictation practice audio, transcription or stenography
speed training, or any situation where you need speech paced to an exact
target rate.

Uses Microsoft Edge's free neural TTS voices via the
[`edge-tts`](https://github.com/rany2/edge-tts) library. Synthesizes the
entire input text in a single API call, uses the returned per-word
timing metadata to slice out each word, then reassembles the words with
calculated silence gaps to hit the exact target WPM.

Notes
- Requires internet access at runtime (free, no API key)
- the edge-tts library essentially reverse-engineers Microsoft's
  API, so this is not officially supported and may break without warning.

### Requirements

```bash
pip install edge-tts pydub
```

`ffmpeg` must also be installed and on your `PATH` (used by `pydub`):

```bash
# macOS
brew install ffmpeg

# Debian/Ubuntu
sudo apt install ffmpeg
```

Windows: see the [ffmpeg downloads page](https://ffmpeg.org/download.html).

### Basic Usage

```bash
python3 dictate_wpm.py input.txt --wpm 10 -o output.mp3
```

### Options

| Flag | Description | Default |
|---|---|---|
| `--wpm` | Target average words-per-minute (required) | — |
| `--voice` | edge-tts voice name | `en-US-MichelleNeural` |
| `--rate` | Overall speaking rate adjustment, e.g. `-10%` or `+15%` | `+0%` |
| `-o`, `--output` | Output audio file path | `output.mp3` |

Run `edge-tts --list-voices` to see all available voices.

Note: if any of the arguments give you errors, try to format like: `--rate="-10%"`

### Examples

Slow 10 WPM dictation practice audio:

```bash
python3 dictate_wpm.py input.txt --wpm 10 -o output.mp3
```

Different voice:

```bash
python3 dictate_wpm.py input.txt --wpm 10 --voice en-US-GuyNeural -o output.mp3
```

If a target WPM is reported as unachievable (too fast for natural word
lengths), speed up the underlying speech itself:

```bash
python3 dictate_wpm.py input.txt --wpm 225 --rate "+80%" -o output.mp3
```

## Known issues

- **`edge-tts` is an unofficial, reverse-engineered client** for Microsoft
  Edge's online TTS service — not an officially supported Microsoft API. It
  can break if Microsoft changes that service.
- Word-boundary timing precision can vary slightly by voice/language, since
  it comes from an unofficial API rather than a documented spec.
