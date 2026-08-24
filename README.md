# ComfyUI H3 Segment Cache

[中文说明](README_ZH.md)

Custom ComfyUI nodes for caching MiniMax H3 video segments to disk, joining them into one final video, and showing the finished video directly on the final node.

The public node name is `H3SegmentCacheFinalize`. It contains the newer preview-capable implementation; there is no separate `H3SegmentCacheFinalizeV2` node.

## Nodes

- `H3SegmentCacheStart`: encodes the first image/audio segment and creates a cache token.
- `H3FrameHandoff`: selects the frame passed to the next segment and optionally trims the exported frames/audio before it.
- `H3SegmentCacheAppend`: encodes each later segment without keeping all decoded frames in memory.
- `H3SegmentCacheFinalize`: joins cached segments, saves the final video, and returns a ComfyUI video preview plus a download link.

FFmpeg is discovered from the system first and then from `imageio-ffmpeg`.

## Install

From the `ComfyUI/custom_nodes` directory:

```bash
git clone https://github.com/Aeverlumi/ComfyUI-H3-Segment-Cache.git
cd ComfyUI-H3-Segment-Cache
python -m pip install -r requirements.txt
```

Use the Python executable that starts ComfyUI. For Windows portable builds, run:

```powershell
..\..\python_embeded\python.exe -m pip install -r requirements.txt
```

Restart ComfyUI after installation. If the node UI was already open, hard-refresh the browser so `web/h3_segment_cache_preview.js` is loaded.

## Workflow Templates

The `workflow_templates` directory contains:

- `minimaxh3_for_loop_motion_context_v8.5_24GB_无Latent放大_无二采.json`: recommended for 24 GB VRAM. It uses one complete sampling pass per segment, with no latent upscaler and no second sampling pass.
- `minimaxh3_for_loop_motion_context_v8.5_32GB_保留Latent放大_保留二采.json`: experimental 32 GB+ VRAM version. It keeps 1.2x latent upscaling, conditioning synchronization, and a low-sigma second pass. Peak VRAM depends on resolution, frame count, model, and ComfyUI offloading, so 32 GB is not an unconditional guarantee.

The 24 GB template intentionally removes the unused latent model loader from the original canvas. Other node titles, notes, prompts, and Load Image nodes are preserved.

## Workflow Dependencies

Use a recent ComfyUI build with the native MiniMax H3 nodes. Install these custom-node repositories for both templates:

- [ComfyUI-H3-Motion-Context](https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context)
- [ComfyUI-KJNodes](https://github.com/kijai/ComfyUI-KJNodes)
- [ComfyUI-Easy-Use](https://github.com/BarnettZhou/ComfyUI-Easy-Use)
- [ComfyUI_Comfyroll_CustomNodes](https://github.com/Suzie1/ComfyUI_Comfyroll_CustomNodes)
- [ComfyUI-UniversalToolkit](https://github.com/whmc76/ComfyUI-UniversalToolkit)

The 32 GB latent-upscale template additionally requires:

- [Comfyui_Minimax_h3_latent_Upscaler](https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler)
- [ComfyUI-YCNodes-MiniMax-H3](https://github.com/yichengup/ComfyUI-YCNodes-MiniMax-H3)

These are external dependencies and are not bundled in this repository. ComfyUI Manager can install missing nodes after the workflow is loaded.

## Models

Both templates reference these filenames:

```text
minimax_h3_video_vae_fp16.safetensors
minimax_h3_audio_vae_fp32.safetensors
minimax_h3_fl2va_pruned_int8_convrot.safetensors
minimax_h3_ref2va_pruned_int8_convrot.safetensors
qwen3vl_32b_minimax_h3_int4_convrot.safetensors
minimax_h3_ref2v_lightx2v_turbo_4step_v0.1_resized_avg_rank_20_bf16.safetensors
```

The 32 GB template also references:

```text
minimax_h3_latent_upscaler_3d_fp16.safetensors
```

Place each model in the folder used by its corresponding ComfyUI loader. The latent upscaler checkpoint belongs in `ComfyUI/models/latent_upscale_models/`.

## Output and Recovery

Final files are written to `ComfyUI/output/h3_long_video/` when `save_output` is enabled. In-progress segments are stored in `ComfyUI/output/.h3_segment_cache/<token>/`. A successful finalize removes that segment cache; if execution stops early, the cache remains so it can be inspected or deleted manually.

## Development

```bash
python -m unittest discover -s tests -v
python -m py_compile __init__.py nodes.py
node --check web/h3_segment_cache_preview.js
```

## License

MIT. Workflow dependencies and model files keep their own licenses and terms.
