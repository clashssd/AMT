"""
Генератор файлов для AMT (страница «Генерация»).

ИИ (через /api/chat) возвращает spec+content. Этот модуль превращает
спецу + контент в реальные байты файла и в HTML-превью (чтобы пользователь
мог посмотреть файл прямо в браузере приложения).

Поддерживаемые типы: docx, xlsx, pptx, pdf, py, md, html, json, csv, txt.
Фото/видео/аудио — заглушки (страницы есть, реализация позже).
"""
import io
import json
import csv
import base64
from typing import Optional


# ===== Генерация бинарных/документных файлов =====

def gen_docx(content: str, title: str = "Документ") -> bytes:
    """content: plain text with Markdown-ish markers (# for headings, - for bullets),
    or JSON {"title":..,"paragraphs":[..],"tables":[{"headers":[..],"rows":[[..]}],
    "styles":{"font":"Arial","size":12,"color":"#333333"},
    "header":"..","footer":"..","image_b64":"..."}"""
    from docx import Document
    from docx.shared import Pt, RGBColor, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    data = None
    if content.strip().startswith("{"):
        try:
            data = json.loads(content)
        except Exception:
            data = None

    doc = Document()

    # Global style
    style_cfg = {}
    if isinstance(data, dict):
        style_cfg = data.get("styles", {})
        title = data.get("title", title)
        paragraphs = data.get("paragraphs", [])
        tables = data.get("tables", [])
        header_text = data.get("header", "")
        footer_text = data.get("footer", "")
        img_b64 = data.get("image_b64", "")
    else:
        paragraphs = []
        tables = []
        header_text = ""
        footer_text = ""
        img_b64 = ""

    # Apply global font to Normal style
    if style_cfg:
        try:
            style = doc.styles["Normal"]
            font = style.font
            if style_cfg.get("font"):
                font.name = style_cfg["font"]
            if style_cfg.get("size"):
                font.size = Pt(int(style_cfg["size"]))
            if style_cfg.get("color"):
                hex_c = style_cfg["color"].lstrip("#")
                font.color.rgb = RGBColor.from_string(hex_c)
        except Exception:
            pass

    # Title
    if title:
        doc.add_heading(title, level=0)

    # Header / Footer
    if header_text:
        try:
            doc.sections[0].header.paragraphs[0].text = header_text
        except Exception:
            pass
    if footer_text:
        try:
            doc.sections[0].footer.paragraphs[0].text = footer_text
        except Exception:
            pass

    # Image
    if img_b64:
        try:
            raw_img = base64.b64decode(img_b64)
            img_file = io.BytesIO(raw_img)
            doc.add_picture(img_file, width=Inches(5))
        except Exception:
            pass

    # Tables
    for tbl in tables:
        if not isinstance(tbl, dict):
            continue
        headers = tbl.get("headers", [])
        rows = tbl.get("rows", [])
        if headers or rows:
            try:
                cols = max(len(headers), len(rows[0]) if rows else 0)
                if cols > 0:
                    table = doc.add_table(rows=1, cols=cols)
                    table.style = "Table Grid"
                    for j, h in enumerate(headers):
                        table.cell(0, j).text = str(h)
                        for para in table.cell(0, j).paragraphs:
                            for run in para.runs:
                                run.bold = True
                    for row in rows:
                        if isinstance(row, dict):
                            row = list(row.values())
                        row_cells = table.add_row().cells
                        for j, val in enumerate(row):
                            if j < cols:
                                row_cells[j].text = str(val)
            except Exception:
                pass

    # Paragraphs
    if paragraphs:
        for para_text in paragraphs:
            if isinstance(para_text, dict):
                text = para_text.get("text", "")
                p = doc.add_paragraph(text)
                if para_text.get("bold"):
                    for run in p.runs:
                        run.bold = True
                if para_text.get("italic"):
                    for run in p.runs:
                        run.italic = True
                if para_text.get("underline"):
                    for run in p.runs:
                        run.underline = True
                if para_text.get("align"):
                    p.alignment = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER,
                                   "right": WD_ALIGN_PARAGRAPH.RIGHT, "justify": WD_ALIGN_PARAGRAPH.JUSTIFY}.get(para_text["align"], WD_ALIGN_PARAGRAPH.LEFT)
            else:
                text = str(para_text)
                if text.strip().startswith("#"):
                    doc.add_heading(text.lstrip("# ").strip(), level=1)
                elif text.strip().startswith("## "):
                    doc.add_heading(text.lstrip("# ").strip(), level=2)
                elif text.strip().startswith("- "):
                    doc.add_paragraph(text[2:], style="List Bullet")
                else:
                    doc.add_paragraph(text)
    else:
        # Fallback: parse plain text line-by-line
        for para in (content or "").split("\n"):
            if para.strip().startswith("#"):
                doc.add_heading(para.lstrip("# ").strip(), level=1)
            elif para.strip().startswith("- "):
                doc.add_paragraph(para[2:], style="List Bullet")
            else:
                doc.add_paragraph(para)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# Sanitize a sheet-title string: openpyxl forbids : \ / ? * [ ] (and length > 31)
def _safe_sheet_name(name, default="Лист"):
    import re as _re
    s = _re.sub(r'[:\\/?\[\]]', '', str(name)).strip()
    s = s[:31]  # Excel limit
    return s or default


def gen_xlsx(content: str, title: str = "Лист") -> bytes:
    """content: JSON {"sheets":[{"name":..,"rows":[[..],..],
    "autofilter":true,"merge":"A1:C1","validation":{"col":1,"options":["a","b"]},
    "styles":{"A1":{"bold":true,"color":"#ff0000","font":"Arial"}}},..]} или CSV.
    Optional "chart" key: {"type":"line","title":..,
    "series":[{"name":..,"values":"=Sheet1!B2:B11","color":"#4472C4"}],
    "width":600,"height":400,"position":"D8"}.
    Cell values starting with '=' are treated as formulas."""
    from openpyxl import Workbook
    from openpyxl.utils import column_index_from_string, get_column_letter
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.formatting.rule import ColorScaleRule

    data = None
    if content.strip().startswith("[") or content.strip().startswith("{"):
        try:
            data = json.loads(content)
        except Exception:
            data = None

    if isinstance(data, dict) and "sheets" in data:
        wb = Workbook()
        wb.remove(wb.active)
        sheets = data["sheets"]
        # Normalization: LLM may send sheets as dict instead of list
        if isinstance(sheets, dict):
            sheets = [sheets]
        elif isinstance(sheets, str):
            # Maybe it's a JSON string of a list
            try:
                parsed = json.loads(sheets)
                sheets = parsed if isinstance(parsed, list) else [parsed]
            except Exception:
                sheets = [{"name": "Лист 1", "rows": [[sheets]]}]
        for i, s in enumerate(sheets):
            if not isinstance(s, dict):
                continue
            raw_name = s.get("name", f"Лист {i+1}")
            ws = wb.create_sheet(title=_safe_sheet_name(raw_name, f"Лист {i+1}"))
            rows = s.get("rows", [])
            # If rows is a dict (e.g. {"col1": [...], "col2": [...]}), convert
            if isinstance(rows, dict):
                keys = list(rows.keys())
                cols = [rows[k] for k in keys]
                rows = [keys] + [list(c) for c in zip(*cols)] if cols else []
            for row in rows:
                if isinstance(row, dict):
                    row = list(row.values())
                # Convert numeric strings to actual numbers so formulas work
                cleaned = []
                for val in row:
                    if isinstance(val, str):
                        v = val.strip()
                        # Try int first, then float — but only if it looks like a number
                        if v and not v.startswith("="):
                            try:
                                if "." in v or "e" in v.lower():
                                    cleaned.append(float(v))
                                else:
                                    cleaned.append(int(v))
                            except (ValueError, TypeError):
                                cleaned.append(val)  # keep as string
                        else:
                            cleaned.append(val)
                    else:
                        cleaned.append(val)
                ws.append(cleaned)

            # === Autofilter ===
            af = s.get("autofilter", False)
            if af and rows:
                max_col = max((len(r) for r in rows), default=1)
                ws.auto_filter.ref = f"A1:{get_column_letter(max_col)}{len(rows)}"

            # === Merge cells ===
            merge = s.get("merge", "")
            if merge:
                try:
                    ws.merge_cells(merge)
                except Exception:
                    pass

            # === Data validation (dropdowns) ===
            dv = s.get("validation")
            if dv and isinstance(dv, dict):
                col_letter = get_column_letter(int(dv.get("col", 1)))
                options = dv.get("options", [])
                if options:
                    dv_obj = DataValidation(type="list", formula1=f'"{",".join(str(o) for o in options)}"', allow_blank=True)
                    dv_obj.error = "Выберите значение из списка"
                    dv_obj.errorTitle = "Недопустимое значение"
                    ws.add_data_validation(dv_obj)
                    for r in range(1, len(rows) + 2):
                        dv_obj.add(f"{col_letter}{r}")

            # === Conditional formatting (color scale) ===
            cf = s.get("conditional")
            if cf and isinstance(cf, dict):
                rng = cf.get("range", "A1:B10")
                try:
                    ws.conditional_formatting.add(
                        rng,
                        ColorScaleRule(start_type="min", start_color="FF0000",
                                       mid_type="percentile", mid_value=50, mid_color="FFFF00",
                                       end_type="max", end_color="00FF00"))
                except Exception:
                    pass

            # === Cell styles ===
            styles = s.get("styles", {})
            for cell_ref, style in styles.items():
                try:
                    cell = ws[cell_ref]
                    if style.get("bold"):
                        cell.font = Font(bold=True)
                    if style.get("italic"):
                        cell.font = Font(italic=True)
                    if style.get("underline"):
                        cell.font = Font(underline="single")
                    if style.get("color"):
                        cell.font = Font(color=style["color"].lstrip("#"))
                    if style.get("font"):
                        cell.font = Font(name=style["font"])
                    if style.get("size"):
                        cell.font = Font(size=style["size"])
                    if style.get("fill"):
                        cell.fill = PatternFill(start_color=style["fill"].lstrip("#"), end_color=style["fill"].lstrip("#"), fill_type="solid")
                    if style.get("align"):
                        cell.alignment = Alignment(horizontal=style["align"])
                except Exception:
                    pass

        # === Chart support ===
        chart_spec = data.get("chart")
        if chart_spec and isinstance(chart_spec, dict):
            _add_chart(wb, chart_spec)

    else:
        wb = Workbook()
        ws = wb.active
        ws.title = _safe_sheet_name(title, "Лист")
        if content:
            reader = csv.reader(io.StringIO(content))
            for row in reader:
                ws.append(row)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _add_chart(wb, spec: dict):
    """Create a chart from spec and attach it to the target sheet."""
    from openpyxl.chart import LineChart, BarChart, PieChart, Reference, Series
    from openpyxl.utils import column_index_from_string
    import re as _re

    chart_type = spec.get("type", "line").lower()
    if chart_type == "line":
        chart = LineChart()
    elif chart_type == "bar":
        chart = BarChart()
    elif chart_type == "pie":
        chart = PieChart()
    else:
        chart = LineChart()

    chart.title = spec.get("title", "")
    chart.width = spec.get("width", 600) / 72.0  # cm
    chart.height = spec.get("height", 400) / 72.0

    series_defs = spec.get("series", [])
    if not series_defs:
        return

    target_ws = wb.worksheets[0] if wb.worksheets else wb.active
    cats = None

    for sdef in series_defs:
        name = sdef.get("name", "Series")
        values_ref = sdef.get("values", "")  # e.g. "=Sheet1!B2:B11"
        color = sdef.get("color", "#4472C4")

        # Parse "Sheet1!B2:B11" → sheet name + range
        m = _re.match(
            r'^=([A-Za-zА-Яа-я0-9_]+)!([A-Z]{1,3}[0-9]{1,4}):([A-Z]{1,3}[0-9]{1,4})$',
            values_ref
        )
        if m:
            sheet_name = m.group(1)
            start = m.group(2)
            end = m.group(3)
        else:
            sheet_name = target_ws.title
            start = "B2"
            end = "B11"

        # Find the target sheet (may have been sanitized — try to match)
        src_ws = None
        for ws in wb.worksheets:
            if ws.title == sheet_name or ws.title.lower() == sheet_name.lower():
                src_ws = ws
                break
        if src_ws is None:
            for ws in wb.worksheets:
                if sheet_name.lower().startswith(ws.title[:10].lower()):
                    src_ws = ws
                    break
        if src_ws is None:
            src_ws = target_ws

        # Parse column/row from start/end
        m_start = _re.match(r'^([A-Z]+)(\d+)$', start)
        m_end = _re.match(r'^([A-Z]+)(\d+)$', end)
        col_start = m_start.group(1) if m_start else "B"
        row_start = int(m_start.group(2)) if m_start else 2
        col_end = m_end.group(1) if m_end else "B"
        row_end = int(m_end.group(2)) if m_end else 11

        min_col = column_index_from_string(col_start)
        max_col = column_index_from_string(col_end)

        vals = Reference(src_ws, min_col=min_col, min_row=row_start, max_col=max_col, max_row=row_end)

        s = Series(vals, title=name)
        chart.series.append(s)

        # Categories: first column of the data range
        if cats is None:
            cats = Reference(src_ws, min_col=1, min_row=row_start, max_col=1, max_row=row_end)
            chart.set_categories(cats)

        # Color
        try:
            s.graphicalProperties.solidFill = color
        except Exception:
            pass

    # Position the chart on the target sheet
    position = spec.get("position", "D8")
    target_ws.add_chart(chart, position)


def _is_dark_color(hex_color: str) -> bool:
    """Check if a hex color is dark (for choosing text color)."""
    c = (hex_color or "").lstrip("#")
    if len(c) < 6:
        return False
    r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    # Perceived luminance
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    return lum < 128


def gen_pptx(content: str, title: str = "Презентация") -> bytes:
    """content: JSON {"slides":[{"title":..,"body":..,
    "bg_color":"#1a1a2e","table":{"headers":[..],"rows":[[..]}},
    "image_b64":"...","notes":"...","font":"Arial","font_size":24}]} или строки (по слайду)."""
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN
    import re as _re

    prs = Presentation()
    slides = None
    raw_data = None
    if content.strip().startswith("[") or content.strip().startswith("{"):
        try:
            raw_data = json.loads(content)
            slides = raw_data if isinstance(raw_data, list) else raw_data.get("slides")
        except Exception:
            slides = None
    if not slides:
        slides = [{"title": s.split("\n")[0].strip(), "body": "\n".join(s.split("\n")[1:])}
                  for s in (content or "").split("\f")]

    # Global theme from top-level dict
    theme = {}
    if isinstance(raw_data, dict):
        theme = raw_data.get("theme", {})
    default_font = theme.get("font", "Arial")
    default_bg = theme.get("bg_color", "")

    for i, s in enumerate(slides):
        if not isinstance(s, dict):
            s = {"title": str(s)}
        # Choose layout: 0=title, 1=title+content, 5=title only, 6=blank
        layout_idx = 0 if i == 0 else 1
        if s.get("blank"):
            layout_idx = 6
        elif s.get("body") is None and s.get("title"):
            layout_idx = 5  # title-only for section headers
        try:
            slide = prs.slides.add_slide(prs.slide_layouts[layout_idx])
        except IndexError:
            slide = prs.slides.add_slide(prs.slide_layouts[0])

        # Background color
        bg_color = s.get("bg_color", default_bg)
        if bg_color:
            try:
                bg = slide.background.fill
                bg.solid()
                hex_c = bg_color.lstrip("#")
                bg.fore_color.rgb = RGBColor.from_string(hex_c)
            except Exception:
                pass

        # Title
        ttl = s.get("title", "")
        if ttl:
            if slide.shapes.title is not None:
                slide.shapes.title.text = ttl
                try:
                    for para in slide.shapes.title.text_frame.paragraphs:
                        for run in para.runs:
                            run.font.name = s.get("font", default_font)
                            run.font.size = Pt(int(s.get("font_size", 28)))
                            run.font.bold = True
                            # Dark background → light text; light background → dark text
                            is_dark = _is_dark_color(bg_color)
                            run.font.color.rgb = RGBColor.from_string(
                                "FFFFFF" if is_dark else "1a1a2e"
                            )
                except Exception:
                    pass

        # Body
        body = s.get("body", "")
        if body:
            if len(slide.placeholders) > 1:
                slide.placeholders[1].text = body
                try:
                    for para in slide.placeholders[1].text_frame.paragraphs:
                        for run in para.runs:
                            run.font.name = s.get("font", default_font)
                            run.font.size = Pt(int(s.get("body_font_size", 18)))
                            is_dark = _is_dark_color(bg_color)
                            run.font.color.rgb = RGBColor.from_string(
                                "E8E8F4" if is_dark else "333333"
                            )
                except Exception:
                    pass

        # Table
        tbl = s.get("table")
        if tbl and isinstance(tbl, dict):
            headers = tbl.get("headers", [])
            rows = tbl.get("rows", [])
            if headers or rows:
                try:
                    rows_count = len(rows) + 1
                    cols_count = max(len(headers), len(rows[0]) if rows else 0)
                    if cols_count > 0:
                        left = Inches(0.5)
                        top = Inches(2.0)
                        width = Inches(9.0)
                        height = Inches(4.0)
                        table_shape = slide.shapes.add_table(rows_count, cols_count, left, top, width, height)
                        table = table_shape.table
                        # Headers
                        for j, h in enumerate(headers):
                            cell = table.cell(0, j)
                            cell.text = str(h)
                            cell.fill.solid()
                            cell.fill.fore_color.rgb = RGBColor.from_string("4472C4")
                            for para in cell.text_frame.paragraphs:
                                for run in para.runs:
                                    run.font.color.rgb = RGBColor.from_string("FFFFFF")
                                    run.font.bold = True
                        # Data rows
                        for r_idx, row in enumerate(rows, 1):
                            if isinstance(row, dict):
                                row = list(row.values())
                            for j, val in enumerate(row):
                                if j < cols_count:
                                    table.cell(r_idx, j).text = str(val)
                except Exception:
                    pass

        # Image
        img_b64 = s.get("image_b64", "")
        if img_b64:
            try:
                raw_img = base64.b64decode(img_b64)
                img_file = io.BytesIO(raw_img)
                pic = slide.shapes.add_picture(img_file, Inches(2), Inches(3), width=Inches(5))
            except Exception:
                pass

        # Notes
        notes = s.get("notes", "")
        if notes:
            try:
                notes_slide = slide.notes_slide
                notes_slide.notes_text_frame.text = notes
            except Exception:
                pass

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def gen_pdf(content: str, title: str = "Документ") -> bytes:
    """content: plain text, or JSON {"title":..,"paragraphs":[..],
    "tables":[{"headers":[..],"rows":[[..]}],"styles":{"font":"Helvetica","size":12,"color":"#333333"}}"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas

    data = None
    if content.strip().startswith("{"):
        try:
            data = json.loads(content)
        except Exception:
            data = None

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    MARGIN = 56

    # Global style
    style_cfg = {}
    if isinstance(data, dict):
        style_cfg = data.get("styles", {})
        title = data.get("title", title)
        paragraphs = data.get("paragraphs", [])
        tables = data.get("tables", [])
    else:
        paragraphs = (content or "").split("\n")
        tables = []

    font_family = style_cfg.get("font", "Helvetica")
    font_size = int(style_cfg.get("size", 11))
    color_str = style_cfg.get("color", "#000000")
    try:
        hex_c = color_str.lstrip("#")
        text_color = colors.HexColor(hex_c)
    except Exception:
        text_color = colors.black

    y = h - MARGIN

    # Title
    c.setFont(f"{font_family}-Bold" if font_family == "Helvetica" else font_family, 18)
    c.setFillColor(text_color)
    c.drawString(MARGIN, y, (title or "Документ")[:80])
    y -= 24

    # Tables
    for tbl in tables:
        if not isinstance(tbl, dict):
            continue
        headers = tbl.get("headers", [])
        rows = tbl.get("rows", [])
        if not (headers or rows):
            continue
        cols = max(len(headers), len(rows[0]) if rows else 0)
        if cols == 0:
            continue
        col_width = (w - 2 * MARGIN) / cols
        c.setFont(f"{font_family}-Bold" if font_family == "Helvetica" else font_family, font_size)
        # Header row
        x = MARGIN
        for j, h_txt in enumerate(headers):
            c.drawString(x, y, str(h_txt)[:40])
            x += col_width
        y -= font_size + 4
        c.setFont(font_family, font_size)
        for row in rows:
            if isinstance(row, dict):
                row = list(row.values())
            x = MARGIN
            for j, val in enumerate(row):
                if j < cols:
                    c.drawString(x, y, str(val)[:40])
                    x += col_width
            y -= font_size + 4
            if y < MARGIN + font_size:
                c.showPage()
                c.setFont(font_family, font_size)
                y = h - MARGIN
        y -= 8

    # Paragraphs
    c.setFont(font_family, font_size)
    c.setFillColor(text_color)
    for para in paragraphs:
        text = para.get("text", "") if isinstance(para, dict) else str(para)
        if not text.strip():
            continue
        if y < MARGIN + font_size:
            c.showPage()
            c.setFont(font_family, font_size)
            y = h - MARGIN
        c.drawString(MARGIN, y, text[:100])
        y -= font_size + 4

    c.save()
    return buf.getvalue()


def gen_py(content: str, title: str = "main.py") -> bytes:
    return (content or "").encode("utf-8")


# Расширения для «кода на любом языке»
CODE_EXTS = {
    "py": ".py", "js": ".js", "ts": ".ts", "go": ".go", "rs": ".rs",
    "java": ".java", "c": ".c", "cpp": ".cpp", "csharp": ".cs", "php": ".php",
    "rb": ".rb", "swift": ".swift", "kt": ".kt", "sh": ".sh", "sql": ".sql",
    "html": ".html", "txt": ".txt",
}

def gen_code(content: str, title: str = "code.txt", lang: str = "txt") -> bytes:
    return (content or "").encode("utf-8")


def gen_markdown(content: str, title: str = "") -> bytes:
    return (content or "").encode("utf-8")


def gen_html(content: str, title: str = "Страница") -> bytes:
    body = content or ""
    # если ИИ уже вернул полный HTML — как есть, иначе обёртка
    if body.lstrip().lower().startswith("<!doctype") or body.lstrip().lower().startswith("<html"):
        out = body
    else:
        out = (f"<!DOCTYPE html>\n<html lang=\"ru\"><head><meta charset=\"utf-8\">"
               f"<title>{title}</title></head><body>\n{body}\n</body></html>")
    return out.encode("utf-8")


def gen_json(content: str, title: str = "") -> bytes:
    try:
        data = json.loads(content)
        return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    except Exception:
        return (content or "").encode("utf-8")


def gen_csv(content: str, title: str = "") -> bytes:
    return (content or "").encode("utf-8")


def gen_txt(content: str, title: str = "") -> bytes:
    return (content or "").encode("utf-8")


GEN = {
    "docx": gen_docx, "xlsx": gen_xlsx, "pptx": gen_pptx, "pdf": gen_pdf,
    "py": gen_py, "md": gen_markdown, "html": gen_html, "json": gen_json,
    "csv": gen_csv, "txt": gen_txt, "code": gen_code,
}


def generate_file(filetype: str, content: str, title: str = "", lang: str = "") -> tuple[bytes, str]:
    """Возвращает (bytes, filename)."""
    ft = (filetype or "txt").lower().lstrip(".")
    if ft in ("jpg", "jpeg", "png", "webp"):
        raise NotImplementedError("Генерация фото ещё не реализована (страница «Фото»).")
    if ft in ("mp4", "mov", "webm", "avi", "mkv"):
        raise NotImplementedError("Генерация видео ещё не реализована (страница «Видео»).")
    if ft in ("mp3", "wav", "ogg", "flac"):
        raise NotImplementedError("Генерация голоса ещё не реализована (страница «Голос»).")
    if ft not in GEN:
        ft = "txt"
    data = GEN[ft](content, title)
    fname = (title or "file").strip()
    # Для кода на любом языке — правильное расширение
    if ft == "code" and lang:
        ext = CODE_EXTS.get(lang, ".txt")
        if not fname.lower().endswith(ext):
            fname = fname.rsplit(".", 1)[0] + ext if "." in fname else fname + ext
    else:
        if not fname.lower().endswith("." + ft):
            fname = fname + "." + ft
    return data, fname


# ===== HTML-превью (как файл выглядел бы) =====

def preview_html(filetype: str, content: str, data: bytes = None, title: str = "") -> str:
    """Возвращает HTML-страницу-превью, которую можно вставить в <iframe>/<div>."""
    ft = (filetype or "txt").lower().lstrip(".")
    if ft in ("html",):
        return content or ""
    if ft in ("md", "txt", "py", "json", "csv"):
        try:
            import markdown as md
            text = content or ""
        except Exception:
            text = content or ""
        if ft == "md":
            import markdown as md
            body = md.markdown(text, extensions=["tables", "fenced_code"])
        elif ft in ("py", "json"):
            try:
                import pygments
                from pygments.formatters import HtmlFormatter
                from pygments import lexers
                code = text
                if ft == "py":
                    lexer = lexers.get_lexer_by_name("python")
                else:
                    lexer = lexers.get_lexer_by_name("json")
                style = HtmlFormatter(style="native")
                body = pygments.highlight(code, lexer, style)
            except Exception:
                import html as _h
                body = "<pre>" + _h.escape(text) + "</pre>"
        elif ft == "csv":
            import html as _h
            import io as _io
            rows = list(csv.reader(_io.StringIO(text)))
            if rows:
                head = "".join(f"<th>{_h.escape(str(c))}</th>" for c in rows[0])
                body_rows = "".join(
                    "<tr>" + "".join(f"<td>{_h.escape(str(c))}</td>" for c in r) + "</tr>"
                    for r in rows[1:])
                body = f"<table style='border-collapse:collapse;width:100%'>" \
                       f"<thead><tr>{head}</tr></thead><tbody>{body_rows}</tbody></table>"
            else:
                body = "<p>(пусто)</p>"
        else:
            import html as _h
            body = "<pre>" + _h.escape(text) + "</pre>"
        return (f"<html><head><meta charset='utf-8'><title>{title}</title>"
                f"<style>body{{font-family:system-ui;padding:24px;background:#0f0f16;color:#e8e8f4}}"
                f"table{{border-collapse:collapse}}th,td{{border:1px solid rgba(255,255,255,.12);"
                f"padding:6px 10px;text-align:left;font-size:14px}}th{{background:rgba(139,134,201,.12)}}"
                f"pre{{background:rgba(0,0,0,.35);padding:14px;border-radius:10px;overflow:auto;"
                f"color:#d8d4ec;font-size:13px;line-height:1.5}}code{{color:#d8d4ec}}</style>"
                f"</head><body>{body}</body></html>")
    if ft in ("docx", "pdf", "xlsx", "pptx"):
        # xlsx/pptx: пробуем распарсить (если openpyxl/pptx установлены)
        if ft == "xlsx" and data:
            try:
                import openpyxl
                wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
                sheets_html = []
                for ws in wb.worksheets:
                    rows_html = []
                    for row in ws.iter_rows(values_only=True):
                        cells = "".join(f"<td>{str(c) if c is not None else ''}</td>" for c in row)
                        if cells.replace("<td></td>", "").strip() and "<tr>" not in cells:
                            rows_html.append(f"<tr>{cells}</tr>")
                    if rows_html:
                        head = rows_html[0].replace("<td>", "<th>").replace("</td>", "</th>")
                        body = "".join(rows_html[1:])
                        sheets_html.append(
                            f"<div style='margin-bottom:16px'><h3 style='margin:8px 0'>{ws.title}</h3>"
                            f"<div style='overflow:auto;max-height:300px'><table style='border-collapse:collapse;width:100%'>"
                            f"<thead>{head}</thead><tbody>{body}</tbody></table></div></div>")
                if sheets_html:
                    return (f"<html><head><meta charset='utf-8'><title>{title}</title>"
                             f"<style>body{{font-family:system-ui;padding:24px;background:#0f0f16;color:#e8e8f4}}"
                             f"table{{border-collapse:collapse}}th,td{{border:1px solid rgba(255,255,255,.12);"
                             f"padding:6px 10px;text-align:left;font-size:13px}}th{{background:rgba(139,134,201,.12)}}"
                             f"h3{{color:#b8b8d0;font-size:15px}}</style></head><body>"
                             f"<h2>{title or 'Excel'}</h2>{''.join(sheets_html)}</body></html>")
            except Exception:
                pass
        if ft == "pptx" and data:
            try:
                from pptx import Presentation
                import io
                prs = Presentation(io.BytesIO(data))
                slides_html = []
                for i, slide in enumerate(prs.slides, 1):
                    texts = []
                    for shape in slide.shapes:
                        if shape.has_text_frame:
                            for para in shape.text_frame.paragraphs:
                                t = para.text.strip()
                                if t:
                                    texts.append(t)
                    if texts:
                        slides_html.append(f"<div style='margin-bottom:16px;border:1px solid rgba(255,255,255,.1);padding:12px;border-radius:8px'>"
                                           f"<b>Слайд {i}:</b><ul style='margin:8px 0 0 16px'>" +
                                           "".join(f"<li>{t}</li>" for t in texts) + "</ul></div>")
                if slides_html:
                    return (f"<html><head><meta charset='utf-8'><title>{title}</title>"
                             f"<style>body{{font-family:system-ui;padding:24px;background:#0f0f16;color:#e8e8f4}}ul{{list-style:disc}}</style>"
                             f"</head><body><h2>{title or 'Презентация'}</h2>{''.join(slides_html)}</body></html>")
            except Exception:
                pass
        # Фолбэк: бейдж-заглушка
        icon = {"docx": "📄", "pdf": "📕", "xlsx": "📊", "pptx": "📽"}.get(ft, "📦")
        return (f"<html><head><meta charset='utf-8'><title>{title}</title>"
                f"<style>body{{font-family:system-ui;padding:24px;background:#0f0f16;color:#e8e8f4;"
                f"display:flex;flex-direction:column;align-items:center;gap:14px}}"
                f".box{{font-size:64px}}.muted{{color:#8a8aa0;font-size:14px}}</style>"
                f"</head><body><div class='box'>{icon}</div><b>{title or 'Файл'}</b>"
                f"<div class='muted'>Бинарный файл ({ft}). Скачайте, чтобы открыть в соответствующем приложении.</div></body></html>")
    return "<html><body></body></html>"
