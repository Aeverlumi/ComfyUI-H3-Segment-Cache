# ComfyUI H3 分段缓存与最终合并

[English](README.md)

这是一组用于 MiniMax H3 循环长视频工作流的 ComfyUI 自定义节点。它把每一段视频及时编码到磁盘，最后合并成完整视频，并在最终节点内显示视频预览和下载链接。

对外节点名称统一为 `H3SegmentCacheFinalize`。这个名称对应的是带完整预览功能的新实现，不再注册 `H3SegmentCacheFinalizeV2`。

## 节点

- `H3SegmentCacheStart`：缓存第一段图像和音频，创建缓存 token。
- `H3FrameHandoff`：选择交给下一段的衔接帧，并可同步裁切此前输出的图像和音频。
- `H3SegmentCacheAppend`：逐段写入后续视频，避免把所有解码帧长期留在内存。
- `H3SegmentCacheFinalize`：合并全部缓存段，保存完整视频，并返回节点内预览和下载链接。

插件优先使用系统 FFmpeg；找不到时自动使用 `imageio-ffmpeg` 提供的 FFmpeg。

## 安装

在 `ComfyUI/custom_nodes` 目录执行：

```bash
git clone https://github.com/Aeverlumi/ComfyUI-H3-Segment-Cache.git
cd ComfyUI-H3-Segment-Cache
python -m pip install -r requirements.txt
```

这里的 `python` 必须是启动 ComfyUI 的同一个 Python。Windows 便携版可以执行：

```powershell
..\..\python_embeded\python.exe -m pip install -r requirements.txt
```

安装后重启 ComfyUI。如果网页之前已经打开，请强制刷新一次，使前端加载 `web/h3_segment_cache_preview.js`。

## v8.5 工作流

`workflow_templates` 中有两个明确区分的版本：

- `minimaxh3_for_loop_motion_context_v8.5_24GB_无Latent放大_无二采.json`：24GB 显存推荐版。每段只进行一次完整采样，不经过 latent 放大，也不进行二采。
- `minimaxh3_for_loop_motion_context_v8.5_32GB_保留Latent放大_保留二采.json`：32GB 以上显存实验版。保留 1.2 倍 latent 放大、Conditioning 尺寸同步和低 sigma 二采。实际峰值显存还受分辨率、帧数、模型和卸载策略影响，因此 32GB 不是任何设置下都绝对不会爆显存。

24GB 版只额外清除了原画布里完全未被使用的 latent 模型加载器。其他节点名称、节点标题、备注、Prompt 和 Load Image 均保持原样。

## 工作流插件依赖

先把 ComfyUI 更新到包含原生 MiniMax H3 节点的较新版本。两个工作流都需要：

- [ComfyUI-H3-Motion-Context](https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context)
- [ComfyUI-KJNodes](https://github.com/kijai/ComfyUI-KJNodes)
- [ComfyUI-Easy-Use](https://github.com/BarnettZhou/ComfyUI-Easy-Use)
- [ComfyUI_Comfyroll_CustomNodes](https://github.com/Suzie1/ComfyUI_Comfyroll_CustomNodes)
- [ComfyUI-UniversalToolkit](https://github.com/whmc76/ComfyUI-UniversalToolkit)

32GB latent 放大版还需要：

- [Comfyui_Minimax_h3_latent_Upscaler](https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler)
- [ComfyUI-YCNodes-MiniMax-H3](https://github.com/yichengup/ComfyUI-YCNodes-MiniMax-H3)

这些是第三方依赖，本仓库没有复制或重新发布它们的代码。加载工作流后，也可以用 ComfyUI Manager 的“安装缺失节点”功能安装。

## 模型文件

两个版本都引用：

```text
minimax_h3_video_vae_fp16.safetensors
minimax_h3_audio_vae_fp32.safetensors
minimax_h3_fl2va_pruned_int8_convrot.safetensors
minimax_h3_ref2va_pruned_int8_convrot.safetensors
qwen3vl_32b_minimax_h3_int4_convrot.safetensors
minimax_h3_ref2v_lightx2v_turbo_4step_v0.1_resized_avg_rank_20_bf16.safetensors
```

32GB 版另外引用：

```text
minimax_h3_latent_upscaler_3d_fp16.safetensors
```

各模型应放到对应 ComfyUI Loader 使用的模型目录。latent 放大模型放在 `ComfyUI/models/latent_upscale_models/`。

## 输出位置

`save_output=true` 时，最终视频位于 `ComfyUI/output/h3_long_video/`。运行中的分段缓存位于 `ComfyUI/output/.h3_segment_cache/<token>/`。成功合并后缓存会自动删除；任务中途失败时缓存会保留，便于排查，也可以手动清理。

## 许可证

本插件使用 MIT License。第三方节点和模型仍分别遵循各自的许可证与使用条款。
