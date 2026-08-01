// Mobile nav toggle
document.addEventListener('DOMContentLoaded', function () {
  var btn = document.getElementById('nav-open');
  var closeBtn = document.getElementById('nav-close');
  var menu = document.getElementById('nav-mobile');
  if (btn) btn.addEventListener('click', function () { menu.classList.add('open'); });
  if (closeBtn) closeBtn.addEventListener('click', function () { menu.classList.remove('open'); });
});
