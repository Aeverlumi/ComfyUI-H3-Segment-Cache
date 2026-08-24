import gc
import json
import shutil
import subprocess
import uuid
import wave
from pathlib import Path

import numpy as np

try:
    import folder_paths
except ImportError:
    folder_paths = None


def _ffmpeg():
    binary = shutil.which("ffmpeg")
    if binary:
        return binary
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise RuntimeError("FFmpeg was not found. Install VideoHelperSuite or imageio-ffmpeg.") from exc


def _output_root():
    if folder_paths is not None:
        return Path(folder_paths.get_output_directory())
    return Path.cwd() / "output"


def _temp_root():
    if folder_paths is not None:
        return Path(folder_paths.get_temp_directory())
    return Path.cwd() / "temp"


def _validate_token(token):
    token = str(token)
    if len(token) != 32 or any(char not in "0123456789abcdef" for char in token):
        raise ValueError("Invalid H3 segment cache token")
    return token


def _cache_dir(token):
    return _output_root() / ".h3_segment_cache" / _validate_token(token)


def _to_numpy(value):
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


def _write_audio(audio, path):
    if not isinstance(audio, dict) or "waveform" not in audio or "sample_rate" not in audio:
        raise ValueError("Expected AUDIO with waveform and sample_rate")
    waveform = _to_numpy(audio["waveform"])
    sample_rate = int(audio["sample_rate"])
    if sample_rate <= 0:
        raise ValueError(f"Expected a positive audio sample rate, got {sample_rate}")
    if waveform.ndim == 3:
        waveform = waveform[0]
    if waveform.ndim == 1:
        waveform = waveform[None, :]
    if waveform.ndim != 2 or waveform.shape[0] <= 0 or waveform.shape[1] <= 0:
        raise ValueError(f"Expected AUDIO waveform [channels,samples], got {waveform.shape}")
    pcm = np.clip(waveform, -1.0, 1.0)
    pcm = (pcm.T * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(pcm.shape[1])
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())


def _slice_audio(audio, frame_count, fps):
    """Trim an AUDIO dict to the selected number of video frames."""
    if not isinstance(audio, dict) or "waveform" not in audio:
        return audio
    out = dict(audio)
    waveform = audio["waveform"]
    sample_rate = int(audio.get("sample_rate", 44100))
    samples = max(1, int(round(max(1, int(frame_count)) / max(float(fps), 1e-6) * sample_rate)))
    out["waveform"] = waveform[..., :samples]
    return out


def _encode_segment(token, index, images, audio, fps, format, pix_fmt, crf, preset, audio_bitrate, trim_to_audio):
    directory = _cache_dir(token)
    directory.mkdir(parents=True, exist_ok=True)
    frames = _to_numpy(images)
    if frames.ndim != 4 or frames.shape[-1] not in (3, 4):
        raise ValueError(f"Expected IMAGE batch [frames,height,width,channels], got {frames.shape}")
    if frames.shape[0] <= 0 or frames.shape[1] <= 0 or frames.shape[2] <= 0:
        raise ValueError(f"Expected a non-empty IMAGE batch, got {frames.shape}")
    fps = float(fps)
    if not np.isfinite(fps) or fps <= 0:
        raise ValueError(f"Expected a positive finite FPS, got {fps}")
    frames = np.clip(frames[..., :3] * 255.0, 0, 255).astype(np.uint8)
    height, width = frames.shape[1:3]
    base = directory / f"segment_{int(index):05d}"
    raw_video = base.with_suffix(".video.mp4")
    wav_path = base.with_suffix(".wav")
    final_path = base.with_suffix(".mp4")
    codec = {"video/h264-mp4": "libx264", "video/h265-mp4": "libx265"}[format]
    command = [
        _ffmpeg(), "-y", "-loglevel", "error", "-f", "rawvideo",
        "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(fps),
        "-i", "-", "-an", "-c:v", codec, "-preset", preset,
        "-crf", str(int(crf)), "-pix_fmt", pix_fmt, str(raw_video),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    try:
        for frame in frames:
            process.stdin.write(frame.tobytes())
        process.stdin.close()
        return_code = process.wait()
    except Exception:
        if process.poll() is None:
            process.kill()
        process.wait()
        raw_video.unlink(missing_ok=True)
        raise
    finally:
        if process.stdin and not process.stdin.closed:
            process.stdin.close()
    if return_code:
        raw_video.unlink(missing_ok=True)
        raise RuntimeError(f"FFmpeg video encoding failed with exit code {return_code}")
    try:
        _write_audio(audio, wav_path)
        mux_command = [
            _ffmpeg(), "-y", "-loglevel", "error", "-i", str(raw_video), "-i", str(wav_path),
            "-c:v", "copy", "-c:a", "aac", "-b:a", audio_bitrate,
        ]
        if trim_to_audio:
            mux_command.append("-shortest")
        mux_command.append(str(final_path))
        subprocess.run(mux_command, check=True)
    except Exception:
        final_path.unlink(missing_ok=True)
        raise
    finally:
        raw_video.unlink(missing_ok=True)
        wav_path.unlink(missing_ok=True)
    manifest = directory / "manifest.json"
    manifest.write_text(json.dumps({
        "fps": float(fps),
        "format": str(format),
        "pix_fmt": str(pix_fmt),
        "crf": int(crf),
        "preset": str(preset),
        "audio_bitrate": str(audio_bitrate),
        "trim_to_audio": bool(trim_to_audio),
    }, ensure_ascii=True), encoding="utf-8")
    del frames
    gc.collect()
    return token


class H3SegmentCacheStart:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "images": ("IMAGE",), "audio": ("AUDIO",), "fps": ("FLOAT", {"default": 8.0}),
            "format": (["video/h264-mp4", "video/h265-mp4"],),
            "pix_fmt": (["yuv420p", "yuv444p"],),
            "crf": ("INT", {"default": 22, "min": 0, "max": 51, "step": 1}),
            "preset": (["medium", "slow", "fast", "veryfast"],),
            "audio_bitrate": (["192k", "256k", "320k"],),
            "trim_to_audio": ("BOOLEAN", {"default": False}),
        }}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("cache_token",)
    FUNCTION = "start"
    CATEGORY = "H3/Long Video"

    def start(self, images, audio, fps, format, pix_fmt, crf, preset, audio_bitrate, trim_to_audio):
        token = uuid.uuid4().hex
        _encode_segment(token, 0, images, audio, fps, format, pix_fmt, crf, preset, audio_bitrate, trim_to_audio)
        return (token,)


class H3FrameHandoff:
    """Choose a handoff frame and split a decoded segment for long-video loops.

    ``frame_index=-1`` preserves the legacy behavior: the whole segment is
    exported and its last frame is passed forward.  For a non-negative index,
    frames before that index are exported while the chosen frame is returned
    as the next segment's reference image.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "images": ("IMAGE",),
            "audio": ("AUDIO",),
            "frame_index": ("INT", {"default": -1, "min": -1, "step": 1}),
            "fps": ("FLOAT", {"default": 8.0, "min": 0.1}),
        }}

    RETURN_TYPES = ("IMAGE", "AUDIO", "IMAGE", "INT")
    RETURN_NAMES = ("frames_before_handoff", "audio_before_handoff", "handoff_frame", "handoff_index")
    FUNCTION = "split"
    CATEGORY = "H3/Long Video"

    def split(self, images, audio, frame_index, fps):
        total = int(images.shape[0])
        if total <= 0:
            raise ValueError("H3FrameHandoff received an empty IMAGE batch")
        if int(frame_index) == 0:
            raise ValueError("H3FrameHandoff frame_index=0 has no preceding video; use -1 or choose a frame >= 1")
        idx = total - 1 if int(frame_index) < 0 else min(max(int(frame_index), 1), total - 1)
        # -1 keeps the old full-segment export behavior. Explicit selection
        # excludes the selected frame from the preceding clip to avoid a seam
        # duplicate; that frame is used only as the next segment's guide.
        before_count = total if int(frame_index) < 0 else idx
        before = images[:before_count]
        before_audio = audio if int(frame_index) < 0 else _slice_audio(audio, before_count, fps)
        selected = images[idx:idx + 1]
        return before, before_audio, selected, idx


class H3SegmentCacheAppend:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "cache_token": ("STRING", {"forceInput": True}),
            "index": ("INT", {"forceInput": True}),
            "images": ("IMAGE",), "audio": ("AUDIO",),
            "fps": ("FLOAT", {"default": 8.0}),
            "format": (["video/h264-mp4", "video/h265-mp4"],),
            "pix_fmt": (["yuv420p", "yuv444p"],),
            "crf": ("INT", {"default": 22, "min": 0, "max": 51, "step": 1}),
            "preset": (["medium", "slow", "fast", "veryfast"],),
            "audio_bitrate": (["192k", "256k", "320k"],),
            "trim_to_audio": ("BOOLEAN", {"default": False}),
            "skip": ("BOOLEAN", {"default": False, "tooltip": "Skip writing this iteration; used to suppress the unavoidable total=1 Easy-Use pass when total duration equals one segment."}),
        }}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("cache_token",)
    FUNCTION = "append"
    CATEGORY = "H3/Long Video"

    def append(self, cache_token, index, images, audio, fps, format, pix_fmt, crf, preset, audio_bitrate, trim_to_audio, skip=False):
        if bool(skip):
            return (cache_token,)
        return (_encode_segment(cache_token, index, images, audio, fps, format, pix_fmt, crf, preset, audio_bitrate, trim_to_audio),)


class H3SegmentCacheFinalize:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "cache_token": ("STRING", {"forceInput": True}),
            "filename_prefix": ("STRING", {"default": "h3_long_video"}),
            "format": (["video/h264-mp4", "video/h265-mp4", "video/webm"],),
            "pix_fmt": (["yuv420p", "yuv444p"],),
            "crf": ("INT", {"default": 22, "min": 0, "max": 51, "step": 1}),
            "preset": (["medium", "slow", "fast", "veryfast"],),
            "audio_bitrate": (["192k", "256k", "320k"],),
            "trim_to_audio": ("BOOLEAN", {"default": False}),
            "save_output": ("BOOLEAN", {"default": True}),
        }}

    RETURN_TYPES = ("VHS_FILENAMES",)
    RETURN_NAMES = ("Filenames",)
    FUNCTION = "finalize"
    CATEGORY = "H3/Long Video"
    OUTPUT_NODE = True

    def finalize(
        self,
        cache_token,
        filename_prefix,
        format="video/h264-mp4",
        pix_fmt="yuv420p",
        crf=22,
        preset="medium",
        audio_bitrate="192k",
        trim_to_audio=False,
        save_output=True,
    ):
        directory = _cache_dir(cache_token)
        segments = sorted(directory.glob("segment_*.mp4"))
        if not segments:
            raise RuntimeError("No cached H3 segments were found")
        output_root = _output_root() if bool(save_output) else _temp_root()
        output_dir = output_root / "h3_long_video"
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_prefix = Path(str(filename_prefix or "h3_long_video")).name
        extension = "webm" if format == "video/webm" else "mp4"
        filename = f"{safe_prefix}_{cache_token[:8]}.{extension}"
        output_path = output_dir / filename
        concat_file = directory / "concat.txt"
        manifest = directory / "manifest.json"
        def concat_entry(path):
            escaped = path.resolve().as_posix().replace("'", "'\\''")
            return f"file '{escaped}'"

        concat_file.write_text("\n".join(concat_entry(path) for path in segments), encoding="utf-8")

        metadata = {}
        if manifest.exists():
            try:
                metadata = json.loads(manifest.read_text(encoding="utf-8"))
            except Exception:
                metadata = {}

        # The normal path uses the same settings as Start/Append. In that
        # case the segment streams can be concatenated without another lossy
        # encode. Changing the final format or quality explicitly opts into a
        # single final transcode.
        can_stream_copy = (
            str(metadata.get("format", "")) == str(format)
            and str(metadata.get("pix_fmt", "")) == str(pix_fmt)
            and int(metadata.get("crf", -1)) == int(crf)
            and str(metadata.get("preset", "")) == str(preset)
            and str(metadata.get("audio_bitrate", "")) == str(audio_bitrate)
            and bool(metadata.get("trim_to_audio", False)) == bool(trim_to_audio)
            and format != "video/webm"
        )

        if can_stream_copy:
            mux_args = [
                _ffmpeg(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                "-i", str(concat_file), "-c", "copy", "-movflags", "+faststart",
                str(output_path),
            ]
        elif format == "video/webm":
            video_args = ["-c:v", "libvpx-vp9", "-crf", str(int(crf)), "-b:v", "0",
                          "-pix_fmt", "yuv420p", "-c:a", "libopus", "-b:a", str(audio_bitrate)]
        else:
            codec = "libx265" if format == "video/h265-mp4" else "libx264"
            audio_args = (["-c:a", "copy"]
                          if str(metadata.get("audio_bitrate", "")) == str(audio_bitrate)
                          else ["-c:a", "aac", "-b:a", str(audio_bitrate)])
            video_args = ["-c:v", codec, "-preset", str(preset), "-crf", str(int(crf)),
                          "-pix_fmt", str(pix_fmt), *audio_args]
        if not can_stream_copy:
            mux_args = [
                _ffmpeg(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                "-i", str(concat_file), *video_args,
            ]
            if format != "video/webm":
                mux_args.extend(["-movflags", "+faststart"])
            if bool(trim_to_audio):
                mux_args.append("-shortest")
            mux_args.append(str(output_path))
        subprocess.run(mux_args, check=True)
        # Build the same preview descriptor used by VideoHelperSuite's
        # VHS_VideoCombine.  ComfyUI only renders a media preview when the
        # output-node UI payload contains this exact `gifs` entry.
        relative_subfolder = "h3_long_video"
        preview = {
            "filename": filename,
            "subfolder": relative_subfolder,
            "type": "output" if bool(save_output) else "temp",
            "format": str(format),
            "frame_rate": float(metadata.get("fps", 8.0)),
            "workflow": filename,
            "fullpath": str(output_path),
        }
        result = {
            "ui": {"gifs": [preview], "videos": [preview]},
            "result": ((bool(save_output), [str(output_path)]),),
        }
        # The per-segment files are no longer needed after concat, but remove
        # them only after the UI payload has been assembled.
        shutil.rmtree(directory, ignore_errors=True)
        return result


NODE_CLASS_MAPPINGS = {
    "H3SegmentCacheStart": H3SegmentCacheStart,
    "H3FrameHandoff": H3FrameHandoff,
    "H3SegmentCacheAppend": H3SegmentCacheAppend,
    "H3SegmentCacheFinalize": H3SegmentCacheFinalize,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "H3SegmentCacheStart": "H3 Segment Cache - Start",
    "H3FrameHandoff": "H3 Frame Handoff (Manual Frame)",
    "H3SegmentCacheAppend": "H3 Segment Cache - Append",
    "H3SegmentCacheFinalize": "H3 Segment Cache - Finalize",
}
