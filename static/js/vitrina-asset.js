document.addEventListener('DOMContentLoaded', function() {
  var burgerBtn = document.getElementById('burger-btn');
  var nav = document.getElementById('nav');

  if (burgerBtn && nav) {
    burgerBtn.addEventListener('click', function() {
      burgerBtn.classList.toggle('active');
      nav.classList.toggle('active');
      var isExpanded = burgerBtn.classList.contains('active');
      burgerBtn.setAttribute('aria-expanded', isExpanded);
      document.body.classList.toggle('menu-open', isExpanded);
    });
  }

  function smoothToggle(el, show) {
    if (show) {
      el.style.maxHeight = el.scrollHeight + 'px';
      el.style.opacity = '1';
      el.addEventListener('transitionend', function handler() {
        if (el.style.maxHeight !== '0px') {
          el.style.maxHeight = 'none';
        }
        el.removeEventListener('transitionend', handler);
      });
    } else {
      el.style.maxHeight = el.scrollHeight + 'px';
      el.offsetHeight; // force reflow
      el.style.maxHeight = '0px';
      el.style.opacity = '0';
    }
  }

  var btnToggleExtra = document.getElementById('btn-toggle-extra');
  var filterExtra = document.getElementById('filter-extra');

  if (btnToggleExtra && filterExtra) {
    var hasActiveExtra = false;
    var inputs = filterExtra.querySelectorAll('input');
    for (var i = 0; i < inputs.length; i++) {
      if (inputs[i].value && inputs[i].value.trim() !== '') {
        hasActiveExtra = true;
        break;
      }
    }
    if (hasActiveExtra) {
      filterExtra.style.maxHeight = 'none';
      filterExtra.style.opacity = '1';
      filterExtra.classList.add('show');
      btnToggleExtra.setAttribute('aria-expanded', 'true');
    }

    btnToggleExtra.addEventListener('click', function() {
      var isExpanded = btnToggleExtra.getAttribute('aria-expanded') === 'true';
      btnToggleExtra.setAttribute('aria-expanded', !isExpanded);
      if (!isExpanded) {
        filterExtra.classList.add('show');
        smoothToggle(filterExtra, true);
      } else {
        smoothToggle(filterExtra, false);
        setTimeout(function() { filterExtra.classList.remove('show'); }, 450);
      }
    });
  }

  var searchToggle = document.getElementById('search-filters-toggle');
  var searchExtra = document.getElementById('search-extra-filters');

  if (searchToggle && searchExtra) {
    searchToggle.addEventListener('click', function() {
      var isExpanded = searchToggle.getAttribute('aria-expanded') === 'true';
      searchToggle.setAttribute('aria-expanded', String(!isExpanded));
      if (!isExpanded) {
        searchExtra.classList.add('show');
        smoothToggle(searchExtra, true);
      } else {
        smoothToggle(searchExtra, false);
        setTimeout(function() { searchExtra.classList.remove('show'); }, 450);
      }
    });
  }

  document.querySelectorAll('.faq-question').forEach(function(btn) {
    btn.addEventListener('click', function() {
      var item = btn.closest('.faq-item');
      if (!item) return;
      var answer = item.querySelector('.faq-answer');
      if (!answer) return;
      var wasOpen = item.classList.contains('open');

      if (wasOpen) {
        answer.style.maxHeight = answer.scrollHeight + 'px';
        answer.offsetHeight;
        answer.style.maxHeight = '0px';
        item.classList.remove('open');
      } else {
        item.classList.add('open');
        answer.style.maxHeight = answer.scrollHeight + 'px';
        answer.addEventListener('transitionend', function handler() {
          if (item.classList.contains('open')) {
            answer.style.maxHeight = 'none';
          }
          answer.removeEventListener('transitionend', handler);
        });
      }
    });
  });

  document.querySelectorAll('.faq-item.open').forEach(function(item) {
    var answer = item.querySelector('.faq-answer');
    if (answer) answer.style.maxHeight = 'none';
  });
});
