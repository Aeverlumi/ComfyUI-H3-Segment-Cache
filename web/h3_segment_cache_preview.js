import { app } from '../../../scripts/app.js';
import { api } from '../../../scripts/api.js';

const FINALIZE_WIDGETS = [
    'filename_prefix', 'format', 'pix_fmt', 'crf',
    'preset', 'audio_bitrate', 'trim_to_audio', 'save_output',
];
const FINALIZE_DEFAULTS = [
    'h3_long_video', 'video/h264-mp4', 'yuv420p', 22,
    'medium', '192k', false, true,
];
const FINALIZE_FORMATS = ['video/h264-mp4', 'video/h265-mp4', 'video/webm'];
const FINALIZE_PIX_FMTS = ['yuv420p', 'yuv444p'];
const FINALIZE_PRESETS = ['medium', 'slow', 'fast', 'veryfast'];
const FINALIZE_AUDIO = ['192k', '256k', '320k'];

function validFinalizeValues(values) {
    if (!Array.isArray(values) || values.length < FINALIZE_WIDGETS.length) return false;
    return typeof values[0] === 'string'
        && FINALIZE_FORMATS.includes(values[1])
        && FINALIZE_PIX_FMTS.includes(values[2])
        && Number.isFinite(Number(values[3]))
        && FINALIZE_PRESETS.includes(values[4])
        && FINALIZE_AUDIO.includes(values[5])
        && typeof values[6] === 'boolean'
        && typeof values[7] === 'boolean';
}

function repairedFinalizeValues(node) {
    const raw = Array.isArray(node.widgets_values) ? node.widgets_values : [];
    if (validFinalizeValues(raw)) return raw.slice(0, FINALIZE_WIDGETS.length);

    // Affected ComfyUI versions saved the first two values shifted out when
    // a hidden forceInput widget was present. Recover the remaining six.
    if (FINALIZE_PIX_FMTS.includes(raw[0]) && Number.isFinite(Number(raw[1]))) {
        const shifted = [
            FINALIZE_DEFAULTS[0], FINALIZE_DEFAULTS[1],
            raw[0], raw[1], raw[2], raw[3], raw[4], raw[5],
        ];
        if (validFinalizeValues(shifted)) return shifted;
    }
    return FINALIZE_DEFAULTS.slice();
}

function normalizeFinalizeNode(node) {
    const values = repairedFinalizeValues(node);
    const widgets = Array.isArray(node.widgets) ? node.widgets : [];
    // Remove stale hidden inputs and preview widgets left by older versions.
    node.widgets = widgets.filter((widget) =>
        widget.name !== 'cache_token' && widget.name !== 'h3_video_preview');
    for (const [index, name] of FINALIZE_WIDGETS.entries()) {
        const widget = node.widgets.find((candidate) => candidate.name === name);
        if (widget) widget.value = values[index];
    }
    node.widgets_values = values.slice();

    if (!node.__h3SerializeGuardInstalled) {
        const previousSerialize = node.onSerialize;
        node.onSerialize = function (event) {
            if (previousSerialize) previousSerialize.apply(this, arguments);
            if (event && Array.isArray(event.widgets_values)) {
                event.widgets_values = FINALIZE_WIDGETS.map((name, index) => {
                    const widget = this.widgets?.find((candidate) => candidate.name === name);
                    return widget?.value ?? values[index];
                });
            }
        };
        node.__h3SerializeGuardInstalled = true;
    }
}

function installPreview(node) {
    if (node.__h3PreviewInstalled) return;
    node.__h3PreviewInstalled = true;

    const root = document.createElement('div');
    root.style.width = '100%';
    root.style.display = 'none';

    const video = document.createElement('video');
    video.controls = true;
    video.loop = true;
    video.muted = false;
    video.playsInline = true;
    video.style.width = '100%';
    video.style.display = 'block';
    root.appendChild(video);

    const actions = document.createElement('div');
    actions.style.display = 'flex';
    actions.style.gap = '8px';
    actions.style.marginTop = '6px';
    const download = document.createElement('a');
    download.textContent = '下载最终视频';
    download.target = '_blank';
    download.rel = 'noopener';
    download.download = '';
    download.style.display = 'none';
    download.style.color = '#8ecbff';
    actions.appendChild(download);
    root.appendChild(actions);

    const widget = node.addDOMWidget('h3_video_preview', 'preview', root, {
        serialize: false,
        hideOnZoom: false,
    });
    // Some older frontend builds ignore the option during graph serialization.
    widget.serialize = false;
    widget.computeSize = function(width) {
        if (!root.style.display || root.style.display === 'none') return [width, -4];
        const ratio = Number(widget.aspectRatio) || 16 / 9;
        return [width, Math.max(80, (width - 20) / ratio + 10)];
    };

    video.addEventListener('loadedmetadata', () => {
        if (video.videoWidth && video.videoHeight) {
            widget.aspectRatio = video.videoWidth / video.videoHeight;
        }
        root.style.display = 'block';
        node.setDirtyCanvas(true, true);
    });
    video.addEventListener('error', () => {
        root.style.display = 'none';
        node.setDirtyCanvas(true, true);
    });

    const update = (params) => {
        if (!params || !params.filename) return;
        const query = new URLSearchParams({
            filename: params.filename,
            subfolder: params.subfolder || '',
            type: params.type || 'output',
            t: String(Date.now()),
        });
        root.value = params;
        const url = api.apiURL('/view?' + query.toString());
        video.src = url;
        download.href = url;
        download.download = params.filename;
        download.style.display = 'inline-block';
        root.style.display = 'block';
        node.setDirtyCanvas(true, true);
    };

    const originalExecuted = node.onExecuted;
    node.onExecuted = function(message) {
        if (originalExecuted) originalExecuted.apply(this, arguments);
        const item = message?.gifs?.[0] || message?.videos?.[0];
        if (item) update(item);
    };
}

app.registerExtension({
    name: 'H3SegmentCache.Preview',
    nodeCreated(node) {
        if (node.comfyClass === 'H3SegmentCacheFinalize' || node.type === 'H3SegmentCacheFinalize') {
            normalizeFinalizeNode(node);
            installPreview(node);
        }
    },
    loadedGraphNode(node) {
        if (node.comfyClass === 'H3SegmentCacheFinalize' || node.type === 'H3SegmentCacheFinalize') {
            normalizeFinalizeNode(node);
            installPreview(node);
        }
    },
});
