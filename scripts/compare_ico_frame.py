from PIL import Image
a = Image.open(r"C:\Users\berds\AppData\Local\Temp\opencode\rsrc_dump\favicon_256_frame.png").convert("RGBA")
b = Image.open(r"C:\Users\berds\AppData\Local\Temp\opencode\rsrc_dump\embedded_256.png").convert("RGBA")
combo = Image.new("RGBA", (a.width + b.width + 16, max(a.height, b.height)), (255,255,255,255))
combo.paste(a, (0,0), a)
combo.paste(b, (a.width + 16, 0), b)
combo.save(r"C:\Users\berds\AppData\Local\Temp\opencode\rsrc_dump\side_by_side.png")
print("saved")
