import { app } from '../../../scripts/app.js';
import { api } from '../../../scripts/api.js';

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
        getValue: () => root.value,
        setValue: (value) => { root.value = value; },
    });
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
            installPreview(node);
        }
    },
});
