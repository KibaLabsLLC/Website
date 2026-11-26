      document.addEventListener('DOMContentLoaded', function () {
        var toggle = document.querySelector('[data-nav-toggle]');
        var drawer = document.querySelector('[data-nav-drawer]');
        if (!toggle || !drawer) return;
        toggle.addEventListener('click', function () {
          var open = drawer.getAttribute('data-open') === 'true';
          drawer.setAttribute('data-open', String(!open));
          toggle.setAttribute('aria-expanded', String(!open));
        });
        drawer.addEventListener('click', function (e) {
          if (e.target.closest('a')) {
            drawer.setAttribute('data-open', 'false');
            toggle.setAttribute('aria-expanded', 'false');
          }
        });
      });

      document.addEventListener('DOMContentLoaded', function () {
        var revealEls = Array.prototype.slice.call(document.querySelectorAll('.reveal'));
        if (!revealEls.length) return;

        var show = function (el) {
          if (el.classList.contains('is-shown')) return;
          var delay = 0;
          var explicit = parseInt(el.getAttribute('data-reveal-delay') || '', 10);
          if (!Number.isNaN(explicit)) {
            delay = explicit;
          } else {
            var group = el.closest('[data-reveal-group]');
            if (group) {
              var groupEls = Array.prototype.slice.call(group.querySelectorAll('.reveal'));
              delay = Math.min(Math.max(groupEls.indexOf(el), 0) * 110, 550);
            }
          }
          el.style.setProperty('--reveal-delay', delay + 'ms');
          el.classList.add('is-shown');
          window.setTimeout(function () { el.style.removeProperty('--reveal-delay'); }, delay + 900);
        };

        var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
        if (reduceMotion.matches || !('IntersectionObserver' in window)) {
          revealEls.forEach(function (el) { el.classList.add('is-shown'); });
          return;
        }

        var observer = new IntersectionObserver(function (entries) {
          entries.forEach(function (entry) {
            if (!entry.isIntersecting) return;
            observer.unobserve(entry.target);
            show(entry.target);
          });
        }, { threshold: 0.15, rootMargin: '0px 0px -7% 0px' });

        revealEls.forEach(function (el) { observer.observe(el); });
      });