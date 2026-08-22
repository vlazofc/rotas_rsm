// One-off generator for favicon assets (PNG + ICO), no external deps.
// Brand color matches --brand in src/styles.css. Run with: node scripts/gen-favicon.cjs
const fs = require("fs");
const path = require("path");
const zlib = require("zlib");

const BRAND = [0x12, 0xa3, 0x86]; // #12a386
const WHITE = [0xff, 0xff, 0xff];

// 5x7 block glyphs on a 32-wide design grid.
const GLYPH_J = [
  [0, 0, 1, 1, 1],
  [0, 0, 0, 1, 0],
  [0, 0, 0, 1, 0],
  [0, 0, 0, 1, 0],
  [1, 0, 0, 1, 0],
  [1, 0, 0, 1, 0],
  [0, 1, 1, 0, 0],
];
const GLYPH_M = [
  [1, 0, 0, 0, 1],
  [1, 1, 0, 1, 1],
  [1, 0, 1, 0, 1],
  [1, 0, 1, 0, 1],
  [1, 0, 0, 0, 1],
  [1, 0, 0, 0, 1],
  [1, 0, 0, 0, 1],
];

const GRID = 32;
const UNIT = 2; // px per glyph cell at GRID=32
const GAP = 2;
const J_W = GLYPH_J[0].length * UNIT;
const M_W = GLYPH_M[0].length * UNIT;
const BLOCK_W = J_W + GAP + M_W;
const BLOCK_H = GLYPH_J.length * UNIT;
const START_X = Math.round((GRID - BLOCK_W) / 2);
const START_Y = Math.round((GRID - BLOCK_H) / 2);

function renderRGBA(size) {
  const scale = size / GRID;
  const buf = Buffer.alloc(size * size * 4);
  const radius = (6 / GRID) * size;
  function inRoundedRect(x, y) {
    const cx = Math.min(Math.max(x + 0.5, radius), size - radius);
    const cy = Math.min(Math.max(y + 0.5, radius), size - radius);
    const dx = (x + 0.5) - cx, dy = (y + 0.5) - cy;
    return (dx * dx + dy * dy) <= radius * radius || (x + 0.5 >= radius && x + 0.5 <= size - radius) || (y + 0.5 >= radius && y + 0.5 <= size - radius);
  }
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const i = (y * size + x) * 4;
      if (size > 16 && !inRoundedRect(x, y)) continue; // leave transparent corners (skip for tiny 16px icon)
      buf[i] = BRAND[0]; buf[i + 1] = BRAND[1]; buf[i + 2] = BRAND[2]; buf[i + 3] = 255;
    }
  }
  function paintGlyph(glyph, offsetXCells) {
    for (let row = 0; row < glyph.length; row++) {
      for (let col = 0; col < glyph[row].length; col++) {
        if (!glyph[row][col]) continue;
        const gx = START_X + offsetXCells * UNIT + col * UNIT;
        const gy = START_Y + row * UNIT;
        const px0 = Math.round(gx * scale);
        const py0 = Math.round(gy * scale);
        const px1 = Math.round((gx + UNIT) * scale);
        const py1 = Math.round((gy + UNIT) * scale);
        for (let py = py0; py < py1; py++) {
          for (let px = px0; px < px1; px++) {
            if (px < 0 || py < 0 || px >= size || py >= size) continue;
            const i = (py * size + px) * 4;
            buf[i] = WHITE[0]; buf[i + 1] = WHITE[1]; buf[i + 2] = WHITE[2]; buf[i + 3] = 255;
          }
        }
      }
    }
  }
  paintGlyph(GLYPH_J, 0);
  paintGlyph(GLYPH_M, GLYPH_J[0].length + GAP / UNIT);
  return buf;
}

function crc32(buf) {
  let c, crc = 0xFFFFFFFF;
  for (let i = 0; i < buf.length; i++) {
    c = (crc ^ buf[i]) & 0xFF;
    for (let k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
    crc = (crc >>> 8) ^ c;
  }
  return (crc ^ 0xFFFFFFFF) >>> 0;
}

function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length, 0);
  const typeBuf = Buffer.from(type, "ascii");
  const crcInput = Buffer.concat([typeBuf, data]);
  const crcBuf = Buffer.alloc(4);
  crcBuf.writeUInt32BE(crc32(crcInput), 0);
  return Buffer.concat([len, typeBuf, data, crcBuf]);
}

function encodePNG(rgba, size) {
  const sig = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  const ihdrData = Buffer.alloc(13);
  ihdrData.writeUInt32BE(size, 0);
  ihdrData.writeUInt32BE(size, 4);
  ihdrData[8] = 8; // bit depth
  ihdrData[9] = 6; // color type RGBA
  ihdrData[10] = 0; ihdrData[11] = 0; ihdrData[12] = 0;
  const ihdr = chunk("IHDR", ihdrData);

  const stride = size * 4;
  const raw = Buffer.alloc((stride + 1) * size);
  for (let y = 0; y < size; y++) {
    raw[y * (stride + 1)] = 0; // filter: none
    rgba.copy(raw, y * (stride + 1) + 1, y * stride, y * stride + stride);
  }
  const idat = chunk("IDAT", zlib.deflateSync(raw, { level: 9 }));
  const iend = chunk("IEND", Buffer.alloc(0));
  return Buffer.concat([sig, ihdr, idat, iend]);
}

function buildICO(pngBuffers) {
  // ICO with embedded PNG payloads (supported since Windows Vista).
  const count = pngBuffers.length;
  const header = Buffer.alloc(6);
  header.writeUInt16LE(0, 0);
  header.writeUInt16LE(1, 2);
  header.writeUInt16LE(count, 4);
  const entries = [];
  const datas = [];
  let offset = 6 + count * 16;
  for (const { size, png } of pngBuffers) {
    const entry = Buffer.alloc(16);
    entry[0] = size >= 256 ? 0 : size;
    entry[1] = size >= 256 ? 0 : size;
    entry[2] = 0; entry[3] = 0;
    entry.writeUInt16LE(1, 4);
    entry.writeUInt16LE(32, 6);
    entry.writeUInt32LE(png.length, 8);
    entry.writeUInt32LE(offset, 12);
    entries.push(entry);
    datas.push(png);
    offset += png.length;
  }
  return Buffer.concat([header, ...entries, ...datas]);
}

const outDir = path.join(__dirname, "..", "public");
const png16 = encodePNG(renderRGBA(16), 16);
const png32 = encodePNG(renderRGBA(32), 32);
const png180 = encodePNG(renderRGBA(180), 180);
const png512 = encodePNG(renderRGBA(512), 512);

fs.writeFileSync(path.join(outDir, "favicon-32.png"), png32);
fs.writeFileSync(path.join(outDir, "apple-touch-icon.png"), png180);
fs.writeFileSync(path.join(outDir, "icon-512.png"), png512);
fs.writeFileSync(path.join(outDir, "favicon.ico"), buildICO([{ size: 16, png: png16 }, { size: 32, png: png32 }]));

console.log("Favicon assets written to", outDir);
