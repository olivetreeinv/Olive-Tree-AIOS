// Motion layer: scroll reveals, stat count-up, nav scroll state.
// Fully guarded behind prefers-reduced-motion; content is visible by default
// in CSS regardless (the .js-motion class, added below, is what opts sections
// into the hidden-until-revealed state).
(function () {
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var nav = document.querySelector('.nav');

  // Nav solid-on-scroll: IntersectionObserver on a sentinel, not a scroll listener.
  var sentinel = document.createElement('div');
  sentinel.style.cssText = 'position:absolute;top:80px;left:0;width:1px;height:1px;';
  document.body.prepend(sentinel);
  if ('IntersectionObserver' in window && nav) {
    var navObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        nav.classList.toggle('is-scrolled', !entry.isIntersecting);
      });
    });
    navObserver.observe(sentinel);
  }

  if (reduce || typeof gsap === 'undefined') return;

  document.documentElement.classList.add('js-motion');
  gsap.registerPlugin(ScrollTrigger);

  // Scroll reveals: fade/translate up 24px, once, on entering viewport.
  document.querySelectorAll('.reveal').forEach(function (el) {
    ScrollTrigger.create({
      trigger: el,
      start: 'top 80%',
      once: true,
      onEnter: function () { el.classList.add('is-revealed'); }
    });
  });

  // Stat count-up on band entry.
  document.querySelectorAll('[data-count]').forEach(function (el) {
    var raw = el.getAttribute('data-count');
    var match = raw.match(/^([^\d]*)([\d.]+)(.*)$/);
    if (!match) return;
    var prefix = match[1], target = parseFloat(match[2]), suffix = match[3];
    var obj = { val: 0 };
    ScrollTrigger.create({
      trigger: el,
      start: 'top 85%',
      once: true,
      onEnter: function () {
        gsap.to(obj, {
          val: target,
          duration: 1.6,
          ease: 'power1.out',
          onUpdate: function () {
            var decimals = (match[2].split('.')[1] || '').length;
            el.textContent = prefix + obj.val.toFixed(decimals) + suffix;
          }
        });
      }
    });
  });
})();
