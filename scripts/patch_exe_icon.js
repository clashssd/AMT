// Patch release\win-unpacked\AMT Chat.exe's embedded icon resources (RT_ICON x4 +
// RT_GROUP_ICON) with frames from our freshly-generated frontend/assets/favicon.ico,
// bypassing electron-builder's silently-failing icon step. Uses resedit's real API:
//   NtExecutable.from(buf) -> NtExecutableResource.from(exe, true)
//   replace entries (5-field shape: {type, id, lang, codepage, bin})
//   resource.outputResource(exe) -> exe.generate() -> write back.
// Usage: node scripts/patch_exe_icon.js
const fs = require('fs');
const path = require('path');
const { NtExecutable, NtExecutableResource, Data } = require('resedit');

// Allow an explicit exe path override (e.g. for patching an already-installed copy
// at %LOCALAPPDATA%\Programs\AMT Chat\AMT Chat.exe), otherwise default to the
// freshly-built release\win-unpacked copy.
const exePath = process.argv[2]
  ? path.resolve(process.argv[2])
  : path.resolve('release', 'win-unpacked', 'AMT Chat.exe');
const icoPath = path.resolve('frontend', 'assets', 'favicon.ico');

if (!fs.existsSync(exePath)) {
  console.error('exe not found:', exePath);
  process.exit(1);
}
if (!fs.existsSync(icoPath)) {
  console.error('ico not found:', icoPath);
  process.exit(1);
}

const IconFileCls = Data && Data.IconFile;
if (!IconFileCls) {
  console.error('could not locate resedit Data.IconFile');
  process.exit(1);
}

const icoBuf = fs.readFileSync(icoPath);
const iconFile = IconFileCls.from(icoBuf);
const icons = iconFile.icons; // [{width, height, bitCount, colors, planes, data}, ...]
console.log('parsed', icons.length, 'frames from favicon.ico:',
  icons.map(i => `${i.width}x${i.height}`).join(', '));

function pickFrame(size) {
  const exact = icons.find(i => i.width === size && i.height === size);
  if (exact) return exact;
  const larger = icons.filter(i => i.width >= size).sort((a, b) => a.width - b.width);
  if (larger.length) return larger[0];
  const smaller = icons.filter(i => i.width < size).sort((a, b) => b.width - a.width);
  if (smaller.length) return smaller[0];
  throw new Error('no usable frame for target size ' + size);
}

// Match the 4-entry RT_ICON layout electron-builder already produced in the .exe
// (ids 1,2,3,4 = 16,32,48,256 px; lang 1033; codepage unchanged from existing entries).
const targetSizes = [16, 32, 48, 256];

const buf = fs.readFileSync(exePath);
const exe = NtExecutable.from(buf);
const resource = NtExecutableResource.from(exe, true);

const codepages = {};
for (const e of resource.entries) {
  if (e.type === 3 || e.type === 14) codepages[e.type + ':' + e.id + ':' + e.lang] = e.codepage;
}

// 1) Replace each RT_ICON payload (type=3) with the matching-size frame's raw bytes.
targetSizes.forEach((size, idx) => {
  const entryId = idx + 1;
  const frame = pickFrame(size);
  const rawBin = frame.data.isIcon() ? frame.data.generate() : frame.data.bin;
  const codepage = codepages['3:' + entryId + ':1033'] || 0;
  resource.replaceResourceEntry({
    type: 3,
    id: entryId,
    lang: 1033,
    codepage,
    bin: rawBin,
  });
  console.log(`patched RT_ICON id=${entryId} (target ${size}px) <- ${frame.width}px frame, ${rawBin.byteLength || rawBin.length} bytes`);
});

// 2) Rebuild the RT_GROUP_ICON descriptor (type=14, id=1) to stay consistent with
//    the 4 (possibly re-picked) frames now embedded as RT_ICON 1..4.
const rebuilt = new IconFileCls(null);
rebuilt.icons = targetSizes.map((size, idx) => {
  const frame = pickFrame(size);
  const rawBin = frame.data.isIcon() ? frame.data.generate() : frame.data.bin;
  return {
    width: size,
    height: size,
    colors: frame.colors,
    planes: frame.planes,
    bitCount: frame.bitCount,
    data: {
      isIcon: () => frame.data.isIcon(),
      generate: () => rawBin,
      bin: rawBin,
      width: size,
      height: size,
      bitCount: frame.bitCount,
    },
  };
});
const groupBin = rebuilt.generate();
const groupCodepage = codepages['14:1:1033'] || 0;
resource.replaceResourceEntry({
  type: 14,
  id: 1,
  lang: 1033,
  codepage: groupCodepage,
  bin: groupBin,
});
console.log('patched RT_GROUP_ICON id=1, rebuilt descriptor, ' + (groupBin.byteLength || groupBin.length) + ' bytes');

// 3) Serialize back and write.
resource.outputResource(exe);
const outBuf = exe.generate();
const outBytes = Buffer.isBuffer(outBuf) ? outBuf : Buffer.from(outBuf);
fs.writeFileSync(exePath, outBytes);
console.log('wrote patched exe ->', exePath, outBytes.length, 'bytes');
