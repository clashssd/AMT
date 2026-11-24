import struct, sys
exe_path = r"C:\Users\berds\Desktop\AMT — копия\release\win-unpacked\AMT Chat.exe"
with open(exe_path,'rb') as f:
    data = f.read()
e_lfanew = struct.unpack_from('<I', data, 0x3C)[0]
numsections = struct.unpack_from('<H', data, e_lfanew+6)[0]
optsize = struct.unpack_from('<H', data, e_lfanew+20)[0]
secstart = e_lfanew+24
sections2=[]
for i in range(numsections):
    off = secstart + i*40
    name = data[off:off+8].rstrip(b'\x00').decode('latin1')
    vsize, vaddr, rawsize, rawptr = struct.unpack_from('<IIII', data, off+8)
    sections2.append((name, vaddr, rawsize, rawptr))
    print(f"section {name!r} vaddr={vaddr:#x} rawptr={rawptr:#x} rawsize={rawsize:#x}")

def rva_to_off(rva):
    for name, vaddr, rawsize, rawptr in sections2:
        if vaddr <= rva < vaddr+max(rawsize,1):
            return rawptr + (rva - vaddr)
    return None

opt = e_lfanew+24
magic = struct.unpack_from('<H', data, opt)[0]
dd = opt+96 if magic==0x20b else opt+112
rsrc_rva, rsrc_size = struct.unpack_from('<II', data, dd+2*8)
print(f"rsrc_rva={rsrc_rva:#x} rsrc_size={rsrc_size:#x} magic={magic:#x}")
rsrc_off = rva_to_off(rsrc_rva)
print(f"rsrc_off={rsrc_off:#x}")

def parse_dir(off, depth=0):
    num_named, num_id = struct.unpack_from('<II', data, off)
    entries=[]
    pos = off+8
    for i in range(num_named+num_id):
        name_or_id, offset_to_data = struct.unpack_from('<II', data, pos)
        pos += 8
        is_name = bool(name_or_id & 0x80000000)
        rid = name_or_id & 0x7FFFFFFF
        if offset_to_data & 0x80000000:
            child_dir_rva = offset_to_data & 0x7FFFFFFF
            child_off = rva_to_off(child_dir_rva)
            if depth<5 and child_off is not None:
                sub = parse_dir(child_off, depth+1)
                entries.append((rid, is_name, sub))
            else:
                entries.append((rid, is_name, 'too-deep-or-missing'))
        else:
            entries.append((rid, is_name, offset_to_data))
    return entries

top = parse_dir(rsrc_off)
print("top-level resource entries:", len(top))
def walk(entries, indent=2):
    for rid, is_named, child in entries:
        label = f"id={rid}" + (" (NAMED)" if is_named else "")
        if isinstance(child, list):
            print(" "*indent + label + f" children={len(child)}")
            walk(child, indent+4)
        elif isinstance(child, int):
            print(" "*indent + label + f" data_rva_or_offset={child:#x}" if child else " "*indent + label + " leaf-no-data")

walk(top)
