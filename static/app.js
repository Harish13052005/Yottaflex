document.addEventListener('click', async function (event) {
  const trigger = event.target.closest('.generate-btn');
  if (!trigger) return;
  const mode = trigger.getAttribute('data-mode');
  const output = document.getElementById('generator-output');
  output.textContent = 'Generating dataset...';
  const response = await fetch('/api/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode, seed: 20261022 })
  });
  const data = await response.json();
  output.textContent = JSON.stringify(data, null, 2);
});

const validateBtn = document.getElementById('validate-btn');
if (validateBtn) {
  validateBtn.addEventListener('click', async function () {
    const output = document.getElementById('generator-output');
    output.textContent = 'Running validation...';
    const response = await fetch('/api/validate', { method: 'POST' });
    const data = await response.json();
    output.textContent = JSON.stringify(data, null, 2);
  });
}
