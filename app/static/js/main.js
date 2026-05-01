document.addEventListener('DOMContentLoaded', () => {
  const chip = document.querySelector('[data-health-chip]');

  if (chip) {
    fetch('/health', { method: 'GET' })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        return response.json();
      })
      .then((payload) => {
        if (payload.status === 'ok') {
          chip.textContent = 'Backend : en ligne';
          chip.classList.add('ok');
        } else {
          chip.textContent = 'Backend : état inconnu';
        }
      })
      .catch(() => {
        chip.textContent = 'Backend : indisponible';
        chip.classList.remove('ok');
      });
  }

  const kpiTargets = document.querySelectorAll('[data-kpi]');
  if (kpiTargets.length === 0) {
    return;
  }

  fetch('/api/kpis', { method: 'GET' })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      return response.json();
    })
    .then((payload) => {
      kpiTargets.forEach((node) => {
        const key = node.getAttribute('data-kpi');
        if (key && Object.prototype.hasOwnProperty.call(payload, key)) {
          node.textContent = String(payload[key]);
        }
      });
    })
    .catch(() => {
      kpiTargets.forEach((node) => {
        node.textContent = '-';
      });
    });
});
