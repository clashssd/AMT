// Пример frontend-расширения.
// Функция init(ctx) вызывается после загрузки.
// ctx = { api: {fetch}, ui: {registerPage, showPage}, project, tools }
//
// Регистрируем новую страницу в сайдбаре и добавляем кнопку.
function init(ctx) {
    // registerPage добавляет страницу в UI и возвращает элемент
    var page = ctx.ui.registerPage('ext_example', 'Пример', 'ext-example-page',
        '<div class="settings-block">' +
        '  <h3>Пример расширения</h3>' +
        '  <p>Это страница, добавленная расширением. Кнопка ниже звонит в бэкенд.</p>' +
        '  <button id="ext-example-btn" class="test-btn primary">Пинг</button>' +
        '  <div id="ext-example-out" class="test-result"></div>' +
        '</div>'
    );
    var btn = document.getElementById('ext-example-btn');
    if (btn) {
        btn.addEventListener('click', function () {
            // Пр��стая проверка: расширяется через /api/extensions/{name}/index.js
            var out = document.getElementById('ext-example-out');
            if (out) {
                out.textContent = 'Загружено. Расширение example работает.';
                out.className = 'test-result success';
            }
        });
    }
}
