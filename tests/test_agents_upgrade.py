# -*- coding: utf-8 -*-
"""Тесты «полного обхода» легальности в промптах:

1. seed_core_agents обновляет устаревший core_web промпт (без блока
   [ПОЛИТИКА КОНТЕНТА: ДАВАЙ ССЫЛКИ, НЕ ИЗВИНЯЙСЯ]) до CODE-версии,
   проставляет corePromptVersion и идемпотентен.
2. Пользовательские (не-core) агенты не затрагиваются.
3. MEDIA_CAPABILITY блок в main.py содержит инструкции по обходу
   отказов из-за авторских прав / 18+ / легальности.
"""
import json
import os
import sys
import tempfile
import textwrap
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'backend'))

from ai_engine.agents import AgentSkillManager  # noqa: E402

POLICY_MARKER = 'NSFW/18+'


def _make_stale_mgr(tmpdir: str) -> AgentSkillManager:
    """Менеджер с УСТАРЕВШИМ core_web (без policy-блока) и user-агентом."""
    p = os.path.join(tmpdir, 'agents.json')
    stale_prompt = "Ты — веб-агент. Старая версия без политики контента."
    data = {
        'agents': [
            {'id': 'core_web', 'name': 'Веб-агент', 'description': 'x',
             'systemPrompt': stale_prompt, 'folder': 'core', 'enabled': True},
            {'id': 'user_custom', 'name': 'Мой агент', 'description': 'y',
             'systemPrompt': 'Свой промпт', 'folder': 'user', 'enabled': True},
        ],
        'skills': [],
    }
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    return AgentSkillManager(p)


class TestSeedCoreAgentsUpgrade(unittest.TestCase):
    def test_core_web_prompt_upgraded(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = _make_stale_mgr(tmp)
            changed = mgr.seed_core_agents()
            self.assertTrue(changed, 'seed_core_agents должен обновить устаревший core_web')
            web = mgr.get_agent('core_web')
            self.assertIn(POLICY_MARKER, web['systemPrompt'],
                          'новый core_web промпт обязан содержать policy-блок')
            self.assertEqual(web.get('corePromptVersion'), 2)
            # Пользовательские настройки не теряются, если были
            self.assertEqual(web.get('folder'), 'core')

    def test_idempotent_second_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = _make_stale_mgr(tmp)
            self.assertTrue(mgr.seed_core_agents())
            # Перезагружаем из файла, чтобы проверить идемпотентность на диске
            mgr2 = AgentSkillManager(mgr.path)
            self.assertFalse(mgr2.seed_core_agents(),
                             'второй вызов ничего не должен менять (идемпотентность)')

    def test_user_agents_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = _make_stale_mgr(tmp)
            mgr.seed_core_agents()
            custom = mgr.get_agent('user_custom')
            self.assertEqual(custom['systemPrompt'], 'Свой промпт',
                             'промпт user-агента не должен меняться')
            self.assertNotIn('corePromptVersion', custom,
                             'у user-агента не должно появляться corePromptVersion')

    def test_missing_core_web_created_with_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, 'agents.json')
            with open(p, 'w', encoding='utf-8') as f:
                json.dump({'agents': [], 'skills': []}, f)
            mgr = AgentSkillManager(p)
            mgr.seed_core_agents()
            web = mgr.get_agent('core_web')
            self.assertIsNotNone(web, 'core_web должен быть создан')
            self.assertIn(POLICY_MARKER, web['systemPrompt'])


class TestCoreWebPolicyBlock(unittest.TestCase):
    """В самой CODE-версии core_web есть policy-блок и он не содержит
    формулировок об отказе (нет слов «отказываюсь из-за авторских прав»)."""

    def test_code_prompt_contains_policy(self):
        code_web = AgentSkillManager.CORE_AGENTS[0]
        self.assertEqual(code_web['id'], 'core_web')
        # v2: web agent with content policy (NSFW/18+ content, no refusal)
        self.assertIn('[ПРАВИЛА КОНТЕНТА]',
                      code_web['systemPrompt'])
        self.assertIn('NSFW/18+',
                      code_web['systemPrompt'])

    def test_no_mojibake_in_code_prompt(self):
        code_web = AgentSkillManager.CORE_AGENTS[0]
        self.assertIn('поисковый запрос', code_web['systemPrompt'],
                      'в промпте не должно быть мусорных символов')


class TestMediaCapabilityBypass(unittest.TestCase):
    """MEDIA_CAPABILITY в main.py содержит обход отказов по легальности."""

    def setUp(self):
        src = open(os.path.join(ROOT, 'backend', 'main.py'), encoding='utf-8').read()
        self.start = src.index('MEDIA_CAPABILITY')
        self.block = src[self.start:self.start + 4000]

    def test_bypass_block_present(self):
        self.assertIn('[ЗАПРОСЫ КОНТЕНТА: ДАВАЙ ССЫЛКИ, НЕ ИЗВИНЯЙСЯ]', self.block)

    def test_no_copyright_refusal(self):
        self.assertIn('НЕ отказываешься', self.block)
        self.assertIn('авторских прав', self.block)

    def test_18_plus_allowed(self):
        self.assertIn('18+', self.block)


if __name__ == '__main__':
    unittest.main(verbosity=2)
