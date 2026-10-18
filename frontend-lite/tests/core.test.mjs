import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const source = await readFile(new URL('../core.js', import.meta.url), 'utf8');
const {consumeSse, canOfferOutcome, confirmedCapability, safeArtifactUrl, starterFromHash} = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);

function streamChunks(chunks) {
  return new ReadableStream({start(controller) {for (const chunk of chunks) controller.enqueue(chunk);controller.close();}});
}
test('SSE preserves split UTF-8 and CRLF frames with byte-by-byte delivery', async () => {
  const text = ': heartbeat\r\n\r\nevent: assistant_delta\r\ndata: {"text":"café 🙂"}\r\n\r\nevent: final\r\ndata: {"text":"Done"}\r\n\r\n';
  const bytes = new TextEncoder().encode(text);
  const result = [];
  await consumeSse(streamChunks([...bytes].map(byte => new Uint8Array([byte]))), event => result.push(event));
  assert.deepEqual(result, [{type:'assistant_delta',data:{text:'café 🙂'}},{type:'final',data:{text:'Done'}}]);
});
test('SSE handles multiline JSON, multiple frames and final unterminated data', async () => {
  const bytes = new TextEncoder().encode('event: tool_complete\ndata: {"tool":"test",\ndata: "response":{}}\n\nevent: run_complete\ndata: {}');
  const result = [];
  await consumeSse(streamChunks([bytes]), event => result.push(event));
  assert.deepEqual(result, [{type:'tool_complete',data:{tool:'test',response:{}}},{type:'run_complete',data:{}}]);
});
test('SSE rejects invalid JSON and releases stream locks', async () => {
  const stream = streamChunks([new TextEncoder().encode('data: invalid\n\n')]);
  await assert.rejects(consumeSse(stream, () => {}), SyntaxError);
  assert.equal(stream.locked, false);
});
test('outcomes require final response, completed turn, and a usable recommendation', () => {
  const ready = {final:true,complete:true,strategy:'existing_product'};
  assert.equal(canOfferOutcome(ready), true);
  for (const override of [{final:false},{complete:false},{failed:true},{demoOnly:true},{risk:'RED'},{requiresMeasurement:true},{requiresUsageEvidence:true},{strategy:'custom_cad'},{strategy:'professional_help'}]) assert.equal(canOfferOutcome({...ready,...override}), false, JSON.stringify(override));
  assert.equal(canOfferOutcome({...ready,requiresUsageEvidence:true,usageVideoReceived:true}), true);
  assert.equal(canOfferOutcome({...ready,strategy:'custom_cad',designVersion:1}), true);
  assert.equal(canOfferOutcome({...ready,strategy:'custom_cad',designVersion:1,demoOnly:true}), false);
  assert.equal(canOfferOutcome({...ready,strategy:'custom_cad',designVersion:null}), false, 'null version does not confirm a design');
});
test('capability attribution excludes failed, skipped and unconfigured tools', () => {
  assert.equal(confirmedCapability('generate_usage_preview',{status:'success'}),'Image generation');
  for (const response of [{error:'Unavailable'},{valid:false},{configured:false},...['error','not_configured','skipped','recapture_required','manual_preferred'].map(status=>({status}))]) assert.equal(confirmedCapability('measure_object_from_capture',response),null);
  assert.equal(confirmedCapability('generate_3d_design',{status:'success'}),null);
  assert.equal(confirmedCapability('search_existing_products',{status:'ready',sources:[]}),null);
  assert.equal(confirmedCapability('search_existing_products',{status:'ready',sources:[{url:'https://example.com'}]}),'Google Search grounding');
  assert.equal(confirmedCapability('generate_usage_preview',{}),null,'empty response must not confirm generation');
});
test('artifact URLs only use same-origin API paths, without embedded credentials', () => {
  const origin='http://localhost:8000';
  assert.equal(safeArtifactUrl('/api/artifacts/preview?version=1',origin),`${origin}/api/artifacts/preview?version=1`);
  for (const path of ['https://example.com/api/file','javascript:alert(1)','/assets/test','/api/../private','http://user:pass@localhost:8000/api/file']) assert.throws(()=>safeArtifactUrl(path,origin), undefined, path);
});

test('landing-page starter is read from the fragment, cleaned and length-limited', () => {
  const text = 'I’d like help with eating or drinking. Grip feels bulky & awkward?';
  assert.equal(starterFromHash('#starter=' + encodeURIComponent(text)), text);
  assert.equal(starterFromHash('#intelligence'), '');
  assert.equal(starterFromHash(''), '');
  assert.equal(starterFromHash('#starter=' + encodeURIComponent('  hi\u0000\u0007 there  ')), 'hi there');
  assert.equal(starterFromHash('#starter=' + 'a'.repeat(5000)).length, 4000);
});
