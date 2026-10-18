// Native browser STL preview. No installed packages or external scripts.
const MAX_BYTES = 8 * 1024 * 1024;
const MAX_TRIANGLES = 12000;

export function parseStl(buffer) {
  if (!(buffer instanceof ArrayBuffer) || buffer.byteLength > MAX_BYTES) {
    throw new Error('This model is too large for the lightweight preview. Download it to inspect locally.');
  }
  const triangles = [];
  const view = new DataView(buffer);
  const count = buffer.byteLength >= 84 ? view.getUint32(80, true) : 0;
  if (count && 84 + count * 50 === buffer.byteLength) {
    if (count > MAX_TRIANGLES) throw new Error('This detailed model exceeds the preview limit. Download it to inspect locally.');
    for (let i = 0; i < count; i++) {
      const triangle = [];
      for (let j = 0; j < 9; j++) triangle.push(view.getFloat32(84 + i * 50 + 12 + j * 4, true));
      triangles.push(triangle);
    }
  } else {
    const source = new TextDecoder().decode(buffer);
    if (!/^\s*solid\b/i.test(source) || !/\bendsolid\b/i.test(source)) throw new Error('The downloaded file is not a supported STL model.');
    const number = '[+-]?(?:\\d+\\.?\\d*|\\.\\d+)(?:[eE][+-]?\\d+)?';
    const vertices = source.matchAll(new RegExp('\\bvertex\\s+(' + number + ')\\s+(' + number + ')\\s+(' + number + ')(?=\\s|$)', 'gi'));
    let triangle = [];
    for (const match of vertices) {
      triangle.push(Number(match[1]), Number(match[2]), Number(match[3]));
      if (triangle.length === 9) {
        triangles.push(triangle);
        triangle = [];
        if (triangles.length > MAX_TRIANGLES) throw new Error('This detailed model exceeds the preview limit. Download it to inspect locally.');
      }
    }
    if (triangle.length) throw new Error('The STL model contains an incomplete triangle.');
  }
  if (!triangles.length || triangles.some(t => t.some(n => !Number.isFinite(n)))) throw new Error('The STL model has no usable geometry.');
  const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
  for (const t of triangles) for (let j = 0; j < 9; j++) {
    const axis = j % 3;
    min[axis] = Math.min(min[axis], t[j]); max[axis] = Math.max(max[axis], t[j]);
  }
  const center = min.map((n, i) => n / 2 + max[i] / 2);
  const size = Math.max(...max.map((n, i) => n - min[i]));
  if (!Number.isFinite(size) || size <= 0) throw new Error('The STL model has invalid dimensions.');
  return triangles.map(t => t.map((n, i) => (n - center[i % 3]) / size));
}

export function safeModelUrl(url, origin) {
  const resolved = new URL(url, origin);
  if (resolved.origin !== origin || !resolved.pathname.startsWith('/api/') || resolved.username || resolved.password) {
    throw new Error('The model download address is not supported.');
  }
  return resolved.href;
}

async function readModel(response) {
  if (!response.ok) throw new Error('The model could not be loaded. Try downloading it.');
  if (Number(response.headers.get('content-length')) > MAX_BYTES) throw new Error('This model is too large for the lightweight preview. Download it to inspect locally.');
  const reader = response.body.getReader();
  const chunks = []; let length = 0;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > MAX_BYTES) throw new Error('This model is too large for the lightweight preview. Download it to inspect locally.');
      chunks.push(value);
    }
  } finally { await reader.cancel().catch(() => {}); }
  const bytes = new Uint8Array(length); let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  return bytes.buffer;
}

export async function mountStlViewer(container, url) {
  const controller = new AbortController();
  let observer, disposed = false;
  const cleanup = () => { disposed = true; controller.abort(); observer?.disconnect(); };
  const region = document.createElement('section');
  region.className = 'stl-viewer';
  region.setAttribute('aria-label', 'Interactive 3D design preview');
  const status = document.createElement('p');
  status.setAttribute('role', 'status'); status.textContent = 'Loading 3D design…';
  region.append(status); container.replaceChildren(region);
  let timeout;
  try {
    const href = safeModelUrl(url, window.location.origin);
    const download = document.createElement('a');
    download.href = href; download.download = ''; download.textContent = 'Download STL';
    region.append(download);
    timeout = setTimeout(() => controller.abort(), 45000);
    const triangles = parseStl(await readModel(await fetch(href, { signal: controller.signal, redirect: 'error' })));
    clearTimeout(timeout);
    if (disposed) return cleanup;
    const canvas = document.createElement('canvas');
    canvas.tabIndex = 0;
    canvas.setAttribute('aria-label', '3D design. Drag or use arrow keys to rotate. Use plus and minus keys to zoom, and Home to reset.');
    canvas.style.cssText = 'display:block;width:100%;height:280px;touch-action:none;border-radius:12px;background:#f0f5f2;';
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('Your browser cannot display this preview. Download the model to view it.');
    region.insertBefore(canvas, download);
    const controls = document.createElement('div');
    controls.style.cssText = 'display:flex;flex-wrap:wrap;gap:6px;margin:8px 0;';
    region.insertBefore(controls, download);
    let yaw = -0.55, pitch = 0.45, zoom = 1, pointer = null;
    const render = () => {
      if (disposed) return;
      const width = Math.max(1, canvas.clientWidth), height = 280;
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0); ctx.clearRect(0, 0, width, height);
      const cy = Math.cos(yaw), sy = Math.sin(yaw), cp = Math.cos(pitch), sp = Math.sin(pitch);
      const scale = Math.min(width, height) * 0.62 * zoom;
      const projected = triangles.map(t => {
        const points = [];
        for (let j = 0; j < 9; j += 3) {
          const x = t[j] * cy + t[j + 2] * sy, z = -t[j] * sy + t[j + 2] * cy;
          points.push([x, t[j + 1] * cp - z * sp, t[j + 1] * sp + z * cp]);
        }
        return { points, depth: points.reduce((s, p) => s + p[2], 0) };
      }).sort((a, b) => a.depth - b.depth);
      for (const { points: p } of projected) {
        const u = p[1].map((n, i) => n - p[0][i]), v = p[2].map((n, i) => n - p[0][i]);
        const normal = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]];
        const light = Math.abs((normal[0] * 0.3 + normal[1] * 0.4 + normal[2] * 0.85) / (Math.hypot(...normal) || 1));
        ctx.beginPath();
        p.forEach((point, i) => ctx[i ? 'lineTo' : 'moveTo'](width / 2 + point[0] * scale, height / 2 - point[1] * scale));
        ctx.closePath(); ctx.fillStyle = `hsl(158 24% ${39 + Math.min(1, light) * 26}%)`;
        ctx.fill();
      }
    };
    const adjust = (dx = 0, dy = 0, dz = 0) => { yaw += dx; pitch += dy; zoom = Math.min(2.5, Math.max(0.4, zoom + dz)); render(); };
    const reset = () => { yaw = -0.55; pitch = 0.45; zoom = 1; render(); };
    for (const [label, action] of [['Rotate left', () => adjust(-0.25)], ['Rotate right', () => adjust(0.25)], ['Tilt up', () => adjust(0, -0.25)], ['Tilt down', () => adjust(0, 0.25)], ['Zoom in', () => adjust(0, 0, 0.15)], ['Zoom out', () => adjust(0, 0, -0.15)], ['Reset', reset]]) {
      const button = document.createElement('button'); button.type = 'button'; button.textContent = label;
      button.addEventListener('click', action, { signal: controller.signal }); controls.append(button);
    }
    canvas.addEventListener('pointerdown', event => {
      if (event.button !== 0) return;
      canvas.focus(); pointer = { id: event.pointerId, x: event.clientX, y: event.clientY }; canvas.setPointerCapture(event.pointerId);
    }, { signal: controller.signal });
    canvas.addEventListener('pointermove', event => {
      if (!pointer || pointer.id !== event.pointerId) return;
      adjust((event.clientX - pointer.x) * 0.012, (event.clientY - pointer.y) * 0.012);
      pointer.x = event.clientX; pointer.y = event.clientY;
    }, { signal: controller.signal });
    for (const eventName of ['pointerup', 'pointercancel', 'lostpointercapture']) canvas.addEventListener(eventName, () => { pointer = null; }, { signal: controller.signal });
    canvas.addEventListener('keydown', event => {
      const actions = { ArrowLeft: () => adjust(-0.15), ArrowRight: () => adjust(0.15), ArrowUp: () => adjust(0, -0.15), ArrowDown: () => adjust(0, 0.15), '+': () => adjust(0, 0, 0.15), '=': () => adjust(0, 0, 0.15), '-': () => adjust(0, 0, -0.15), Home: reset };
      if (actions[event.key]) { event.preventDefault(); actions[event.key](); }
    }, { signal: controller.signal });
    status.textContent = 'Design preview · fit has not been verified. Drag to rotate.';
    observer = new ResizeObserver(render); observer.observe(canvas); render();
  } catch (error) {
    status.textContent = error.name === 'AbortError'
      ? 'The 3D model took too long to load from artifact storage.'
      : error.message;
    if (error.name === 'AbortError') {
      const retry = document.createElement('button');
      retry.type = 'button';
      retry.textContent = 'Retry 3D preview';
      retry.addEventListener('click', () => { void mountStlViewer(container, url); }, { once: true });
      region.append(retry);
    }
  } finally { clearTimeout(timeout); }
  return cleanup;
}
