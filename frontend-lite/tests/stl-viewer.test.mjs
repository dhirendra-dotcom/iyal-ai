// Optional development checks; Node is not needed to serve or use this app.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
const source = await readFile(new URL('../stl-viewer.js', import.meta.url), 'utf8');
const { parseStl, safeModelUrl } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const ascii = `solid sample
facet normal 0 0 1
outer loop
vertex 0 0 0
vertex 2 0 0
vertex 0 2 0
endloop
endfacet
endsolid sample`;
test('ASCII STL is normalized around its center', () => {
  assert.deepEqual(parseStl(new TextEncoder().encode(ascii).buffer), [[-0.5, -0.5, 0, 0.5, -0.5, 0, -0.5, 0.5, 0]]);
});
test('binary STL is parsed even when its header starts with solid', () => {
  const buffer = new ArrayBuffer(134), view = new DataView(buffer);
  new Uint8Array(buffer).set(new TextEncoder().encode('solid binary'));
  view.setUint32(80, 1, true);
  [0, 0, 0, 2, 0, 0, 0, 2, 0].forEach((v, i) => view.setFloat32(96 + i * 4, v, true));
  assert.deepEqual(parseStl(buffer), parseStl(new TextEncoder().encode(ascii).buffer));
  view.setFloat32(96, NaN, true);
  assert.throws(() => parseStl(buffer), /no usable geometry/);
});
test('malformed and oversized geometry is rejected', () => {
  assert.throws(() => parseStl(new ArrayBuffer(0)), /not a supported STL/);
  assert.throws(() => parseStl(new ArrayBuffer(8 * 1024 * 1024 + 1)), /too large/);
  assert.throws(() => parseStl(new TextEncoder().encode('solid test\nvertex 0 0 0\nendsolid').buffer), /incomplete triangle/);
  const buffer = new ArrayBuffer(84 + 12001 * 50);
  new DataView(buffer).setUint32(80, 12001, true);
  assert.throws(() => parseStl(buffer), /preview limit/);
});
test('downloads remain under same-origin API paths', () => {
  const origin = 'http://localhost:8000';
  assert.equal(safeModelUrl('/api/artifacts/test.stl', origin), `${origin}/api/artifacts/test.stl`);
  for (const url of ['https://example.com/api/test.stl', 'javascript:alert(1)', '/private/test.stl', '/api/../private/test.stl', '//example.com/api/test.stl', 'http://user:pass@localhost:8000/api/test.stl']) {
    assert.throws(() => safeModelUrl(url, origin), /not supported/);
  }
});
