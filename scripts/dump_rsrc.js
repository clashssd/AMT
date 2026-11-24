const fs = require('fs');
const { NtExecutable, NtExecutableResource } = require('resedit');

const exePath = 'C:\\Users\\berds\\Desktop\\AMT — копия\\release\\win-unpacked\\AMT Chat.exe';
const buf = fs.readFileSync(exePath);
const exe = NtExecutable.from(fs.readFileSync(exePath));
const res = NtExecutableResource.from(exe, true);
console.log('total entries:', res.entries.length);
const byType = {};
for (const e of res.entries) {
  byType[e.type] = (byType[e.type] || 0) + 1;
}
console.log('entries by type:', JSON.stringify(byType));
// RT_ICON = 3, RT_GROUP_ICON = 14
for (const e of res.entries) {
  if (e.type === 3 || e.type === 14 || e.type === 'RT_ICON' || e.type === 'RT_GROUP_ICON') {
    console.log(`type=${e.type} id=${e.id} lang=${e.lang} binSize=${e.bin ? e.bin.byteLength : 0} rva=${e.rva}`);
  }
}
// dump all RT_ICON bin blobs to files for inspection
fs.mkdirSync('C:\\Users\\berds\\AppData\\Local\\Temp\\opencode\\rsrc_dump', { recursive: true });
for (const e of res.entries) {
  if (e.type === 3 && e.bin && e.bin.byteLength > 0) {
    const out = `C:\\Users\\berds\\AppData\\Local\\Temp\\opencode\\rsrc_dump\\rticon_${e.id}_${e.lang}.bin`;
    fs.writeFileSync(out, Buffer.from(e.bin));
    console.log('dumped', out, e.bin.byteLength, 'bytes');
  }
}
