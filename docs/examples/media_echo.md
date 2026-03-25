# Media Echo Bot

A bot that receives all message types -- text, images, voice, files, and videos -- and echoes them back. Media messages are downloaded and re-sent.

See [`examples/media_echo.py`](https://github.com/Oaklight/weilink/blob/master/examples/media_echo.py) in the repository.

## Usage

```bash
pip install weilink[media]
python examples/media_echo.py
```

Set the log level with the `LOGLEVEL` environment variable (default: `INFO`):

```bash
LOGLEVEL=DEBUG python examples/media_echo.py
```

## How It Works

1. Logs in and enters the receive loop.
2. Dispatches each incoming message by its `msg_type`:

    - **TEXT** -- replies with `"Echo: <text>"`.
    - **IMAGE** -- downloads the image with `wl.download(msg)`, then re-sends it with `wl.send(user, image=data)`.
    - **VOICE** -- downloads the voice clip. If a transcription is available (`msg.voice.text`), replies with the transcript; otherwise re-sends the audio.
    - **FILE** -- downloads the file and re-sends it, preserving the original filename.
    - **VIDEO** -- downloads the video and re-sends it.

3. All media errors are caught and reported back to the user as text.

## Key Features Demonstrated

- **MessageType enum** -- branching on `MessageType.TEXT`, `IMAGE`, `VOICE`, `FILE`, `VIDEO`.
- **Media download** -- `wl.download(msg)` returns raw `bytes`.
- **Sending media** -- `wl.send()` accepts `image`, `voice`, `file`, `video` keyword arguments.
- **File metadata** -- accessing `msg.file.file_name`, `msg.image.thumb_width`, `msg.voice.playtime`, etc.
