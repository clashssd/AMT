"""Test _auto_wrap_gen_file_tokens — LLM raw JSON auto-wrap to [[GEN:file|...]]"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from main import _auto_wrap_gen_file_tokens


def test_xlsx_json_in_fences_wrapped():
    t = 'Вот готовый файл Excel:\n```json\n{"sheets": [{"name": "Данные и Диаграмма", "rows": [["Кол1", "Кол2"], [1, 2]]}]}\n```\n'
    r = _auto_wrap_gen_file_tokens(t)
    assert '[[GEN:file|xlsx|' in r, f'FAIL: xlsx not wrapped: {r}'


def test_pptx_json_in_fences_wrapped():
    t = 'Вот презентация:\n```json\n{"slides": [{"title": "Слайд 1", "body": "Привет"}]}\n```\n'
    r = _auto_wrap_gen_file_tokens(t)
    assert '[[GEN:file|pptx|' in r, f'FAIL: pptx not wrapped: {r}'


def test_already_has_gen_token_unchanged():
    t = 'Текст [[GEN:file|xlsx|{"sheets":[]}}]'
    r = _auto_wrap_gen_file_tokens(t)
    assert r == t, f'FAIL: should not modify: {r}'


def test_no_json_unchanged():
    t = 'Просто текст без JSON'
    r = _auto_wrap_gen_file_tokens(t)
    assert r == t, f'FAIL: should not modify: {r}'


def test_empty_string():
    assert _auto_wrap_gen_file_tokens('') == ''
    assert _auto_wrap_gen_file_tokens(None) is None or _auto_wrap_gen_file_tokens(None) == ''
