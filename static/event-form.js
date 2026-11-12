(() => {
  const toggle = document.getElementById('id_repeat_weekly');
  const until = document.getElementById('id_repeat_until');
  if (!toggle || !until) return;
  const update = () => {
    until.disabled = !toggle.checked;
    until.required = toggle.checked;
  };
  toggle.addEventListener('change', update);
  window.addEventListener('pageshow', update);
  update();
})();
