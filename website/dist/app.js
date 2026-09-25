const menuButton = document.querySelector('.menu-button');
const mobileNav = document.querySelector('#mobile-nav');

menuButton?.addEventListener('click', () => {
  const isOpen = menuButton.getAttribute('aria-expanded') === 'true';
  menuButton.setAttribute('aria-expanded', String(!isOpen));
  mobileNav.hidden = isOpen;
  document.body.classList.toggle('menu-open', !isOpen);
});

mobileNav?.querySelectorAll('a').forEach((link) => {
  link.addEventListener('click', () => {
    menuButton.setAttribute('aria-expanded', 'false');
    mobileNav.hidden = true;
    document.body.classList.remove('menu-open');
  });
});

const metricButtons = [...document.querySelectorAll('[data-metric]')];
const metricPanels = [...document.querySelectorAll('[data-panel]')];

metricButtons.forEach((button) => {
  button.addEventListener('click', () => {
    const metric = button.dataset.metric;
    metricButtons.forEach((item) => item.setAttribute('aria-pressed', String(item === button)));
    metricPanels.forEach((panel) => { panel.hidden = panel.dataset.panel !== metric; });
  });
});
