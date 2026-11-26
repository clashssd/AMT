// ===== Токены =====
// Простой оценщик токенов для англо-русского текста.
// Для английского: ~4 символа на токен. Для кириллицы: ~2.7 символа.
// Это приближённая оценка, не полная замена tokenizer-а модели.
function estimateTokens(text) {
    if (!text) return 0;
    let cyr = 0, latin = 0, other = 0;
    for (const ch of text) {
        const code = ch.codePointAt(0);
        if (code >= 0x0400 && code <= 0x04FF) cyr++;
        else if (code >= 0x0041 && code <= 0x005A || code >= 0x0061 && code <= 0x007A) latin++;
        else other++;
    }
    const tokens = cyr / 2.7 + latin / 4 + other / 4;
    return Math.ceil(tokens);
}

function estimateTokensForMessages(messages) {
    return messages.reduce((sum, m) => sum + estimateTokens(m.content), 0);
}
