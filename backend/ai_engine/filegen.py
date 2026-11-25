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
    from docx import Document
    from docx.shared import Pt
    doc = Document()
    if title:
        doc.add_heading(title, level=0)
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
    """content: JSON {"sheets":[{"name":..,"rows":[[..],..]},..]} или CSV.
    Optional "chart" key: {"type":"line","title":..,
    "series":[{"name":..,"values":"=Sheet1!B2:B11","color":"#4472C4"}],
    "width":600,"height":400,"position":"D8"}."""
    from openpyxl import Workbook
    from openpyxl.utils import column_index_from_string

    data = None
    if content.strip().startswith("[") or content.strip().startswith("{"):
        try:
            data = json.loads(content)
        except Exception:
            data = None

    if isinstance(data, dict) and "sheets" in data:
        wb = Workbook()
        wb.remove(wb.active)
        for i, s in enumerate(data["sheets"]):
            raw_name = s.get("name", f"Лист {i+1}")
            ws = wb.create_sheet(title=_safe_sheet_name(raw_name, f"Лист {i+1}"))
            for row in s.get("rows", []):
                ws.append(row)

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


def gen_pptx(content: str, title: str = "Презентация") -> bytes:
    """content: JSON {"slides":[{"title":..,"body":..}]} или строки (по слайду)."""
    from pptx import Presentation
    from pptx.util import Inches
    prs = Presentation()
    slides = None
    if content.strip().startswith("[") or content.strip().startswith("{"):
        try:
            j = json.loads(content)
            slides = j if isinstance(j, list) else j.get("slides")
        except Exception:
            slides = None
    if not slides:
        slides = [{"title": s.split("\n")[0].strip(), "body": "\n".join(s.split("\n")[1:])}
                  for s in (content or "").split("\f")]
    for i, s in enumerate(slides):
        if i == 0:
            slide = prs.slides.add_slide(prs.slide_layouts[0])  # title
            slide.shapes.title.text = s.get("title", title)
            if s.get("body"):
                slide.placeholders[1].text = s["body"]
        else:
            slide = prs.slides.add_slide(prs.slide_layouts[1])  # title+body
            slide.shapes.title.text = s.get("title", f"Слайд {i+1}")
            slide.placeholders[1].text = s.get("body", "")
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def gen_pdf(content: str, title: str = "Документ") -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    MARGIN = 56  # ~2cm
    y = h - MARGIN
    c.setFont("Helvetica-Bold", 18)
    c.drawString(MARGIN, y, (title or "Документ")[:80])
    y -= 24
    c.setFont("Helvetica", 11)
    for line in (content or "").split("\n"):
        if y < MARGIN:
            c.showPage()
            c.setFont("Helvetica", 11)
            y = h - MARGIN
        c.drawString(MARGIN, y, line[:110])
        y -= 16
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
