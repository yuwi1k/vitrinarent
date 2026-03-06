/* Полный перенос из Asset-Manager (client/public/script.js): бургер-меню и раскрытие доп. фильтров */
document.addEventListener('DOMContentLoaded', function() {
  // Mobile Menu
  var burgerBtn = document.getElementById('burger-btn');
  var nav = document.getElementById('nav');

  if (burgerBtn && nav) {
    burgerBtn.addEventListener('click', function() {
      burgerBtn.classList.toggle('active');
      nav.classList.toggle('active');
      var isExpanded = burgerBtn.classList.contains('active');
      burgerBtn.setAttribute('aria-expanded', isExpanded);
    });
  }

  // Filter Toggle (главная: #btn-toggle-extra + #filter-extra; поиск: #search-filters-toggle + #search-extra-filters)
  var btnToggleExtra = document.getElementById('btn-toggle-extra');
  var filterExtra = document.getElementById('filter-extra');

  if (btnToggleExtra && filterExtra) {
    btnToggleExtra.addEventListener('click', function() {
      var isExpanded = btnToggleExtra.getAttribute('aria-expanded') === 'true';
      btnToggleExtra.setAttribute('aria-expanded', !isExpanded);
      if (!isExpanded) {
        filterExtra.classList.add('show');
      } else {
        filterExtra.classList.remove('show');
      }
    });
  }

  var searchToggle = document.getElementById('search-filters-toggle');
  var searchExtra = document.getElementById('search-extra-filters');

  if (searchToggle && searchExtra) {
    searchToggle.addEventListener('click', function() {
      var isExpanded = searchToggle.getAttribute('aria-expanded') === 'true';
      searchToggle.setAttribute('aria-expanded', String(!isExpanded));
      searchExtra.classList.toggle('show', !isExpanded);
    });
  }
});
