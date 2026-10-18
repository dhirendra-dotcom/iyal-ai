// Browser-native helpers. No build step, dependencies or remote imports.
export async function consumeSse(stream, onEvent) {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  function drain(flush = false) {
    // Split complete frames before normalizing CRLF: chunks may end mid-CRLF.
    let match;
    while ((match = /\r?\n\r?\n/.exec(buffer))) {
      parse(buffer.slice(0, match.index));
      buffer = buffer.slice(match.index + match[0].length);
    }
    if (flush && buffer.trim()) parse(buffer);
  }
  function parse(block) {
    let type = 'message'; const data = [];
    for (const line of block.split(/\r?\n/)) {
      if (line.startsWith('event:')) type = line.slice(6).trim();
      if (line.startsWith('data:')) data.push(line.slice(5).trimStart());
    }
    if (data.length) onEvent({type, data: JSON.parse(data.join('\n'))});
  }
  try {
    while (true) {
      const {value, done} = await reader.read();
      if (done) { buffer += decoder.decode(); drain(true); break; }
      buffer += decoder.decode(value, {stream:true});
      if (buffer.length > 2_000_000) throw new Error('Response frame is too large.');
      drain();
    }
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
}
export function canOfferOutcome(turn) {
  if (!turn.final || !turn.complete || turn.failed || turn.demoOnly || turn.risk === 'RED') return false;
  if (Number.isInteger(turn.designVersion) && turn.designVersion > 0) return true;
  return Boolean(turn.strategy && !['custom_cad','professional_help'].includes(turn.strategy)
    && !turn.requiresMeasurement && (!turn.requiresUsageEvidence || turn.usageVideoReceived));
}
export function safeArtifactUrl(path, origin) {
  const url = new URL(path, origin);
  if (url.origin !== origin || !url.pathname.startsWith('/api/') || url.username || url.password) throw new Error('Invalid artifact location.');
  return url.href;
}
export function starterFromHash(hash) {
  let value = '';
  try { value = new URLSearchParams(String(hash || '').replace(/^#/, '')).get('starter') || ''; } catch { return ''; }
  // Strip control characters and keep within the chat request limit.
  return value.replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g, '').trim().slice(0, 4000);
}
export const capabilities = {
  present_adaptation_options:'Personalized reasoning', present_measurement_plan:'Measurement planning',
  register_usage_video:'Video context', search_existing_products:'Google Search grounding',
  measure_object_from_capture:'Visual target recognition', generate_usage_preview:'Image generation',
  generate_environment_preview:'Image generation', assess_support_need:'Fit confidence assessment', voice_transcription:'Audio transcription'
};
export function confirmedCapability(tool, response) {
  if (!response || typeof response !== 'object' || Object.keys(response).length === 0) return null;
  if (!capabilities[tool] || response.error || response.valid === false || response.configured === false
    || ['error','not_configured','skipped','recapture_required','manual_preferred'].includes(response.status)) return null;
  if (tool === 'search_existing_products' && !response.sources?.length) return null;
  return capabilities[tool];
}
