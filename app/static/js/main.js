document.addEventListener('DOMContentLoaded', () => {
  const normalizeText = (value) =>
    (value || '')
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '');

  const initAutoToggleForms = () => {
    const candidateForms = document.querySelectorAll(
      'form.form-grid, form.compact-form, form.form-inline-row',
    );
    candidateForms.forEach((form) => {
      if (form.dataset.toggleReady === '1') {
        return;
      }
      if (
        form.classList.contains('inline-form') ||
        form.classList.contains('search-form') ||
        form.closest('[data-no-form-toggle]') ||
        form.dataset.formToggle === 'off' ||
        (form.getAttribute('method') || 'post').toLowerCase() === 'get'
      ) {
        return;
      }

      const toggleWrap = document.createElement('div');
      toggleWrap.className = 'form-toggle-row';

      const toggleButton = document.createElement('button');
      toggleButton.type = 'button';
      const isInlineContext =
        form.classList.contains('form-inline-row') ||
        !!form.closest('.td-actions');
      toggleButton.className = isInlineContext
        ? 'btn btn-primary btn-sm form-toggle-btn'
        : 'btn btn-primary form-toggle-btn';

      const submitButton = form.querySelector('button[type="submit"]');
      const submitLabel = submitButton
        ? submitButton.textContent.trim().replace(/\s+/g, ' ')
        : 'Ajouter';
      const openLabel = form.dataset.formShowLabel || `+ ${submitLabel}`;
      const closeLabel = form.dataset.formHideLabel || 'Fermer';
      let isOpen = form.dataset.formOpen === '1';

      const updateState = () => {
        form.hidden = !isOpen;
        toggleButton.textContent = isOpen ? closeLabel : openLabel;
        toggleButton.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
      };

      toggleButton.addEventListener('click', () => {
        isOpen = !isOpen;
        updateState();
      });

      updateState();

      form.parentNode.insertBefore(toggleWrap, form);
      toggleWrap.appendChild(toggleButton);
      form.dataset.toggleReady = '1';
    });
  };

  const triggerFieldEvents = (field) => {
    field.dispatchEvent(new Event('input', { bubbles: true }));
    field.dispatchEvent(new Event('change', { bubbles: true }));
  };

  const formatDate = (value) => value.toISOString().slice(0, 10);
  const formatDateFr = (value) => {
    const dd = String(value.getDate()).padStart(2, '0');
    const mm = String(value.getMonth() + 1).padStart(2, '0');
    const yyyy = value.getFullYear();
    return `${dd}-${mm}-${yyyy}`;
  };

  const parseDateFromInput = (rawValue) => {
    const raw = (rawValue || '').trim();
    if (!raw) return null;

    const fr = raw.match(/^(\d{2})[-/](\d{2})[-/](\d{4})$/);
    if (fr) {
      const d = Number(fr[1]);
      const m = Number(fr[2]);
      const y = Number(fr[3]);
      return new Date(y, m - 1, d);
    }

    const iso = raw.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (iso) {
      const y = Number(iso[1]);
      const m = Number(iso[2]);
      const d = Number(iso[3]);
      return new Date(y, m - 1, d);
    }

    return null;
  };

  initAutoToggleForms();

  const studentAddForm = document.getElementById('student-add-form');
  if (studentAddForm) {
    studentAddForm.addEventListener('submit', (event) => {
      const birthField = studentAddForm.querySelector(
        'input[name="birth_date"]',
      );
      if (!birthField) {
        return;
      }

      const parsed = parseDateFromInput(birthField.value);
      if (!parsed || Number.isNaN(parsed.getTime())) {
        return;
      }

      const currentYear = new Date().getFullYear();
      const cutoff = new Date(currentYear, 9, 1);
      let age = cutoff.getFullYear() - parsed.getFullYear();
      if (
        parsed.getMonth() > cutoff.getMonth() ||
        (parsed.getMonth() === cutoff.getMonth() &&
          parsed.getDate() > cutoff.getDate())
      ) {
        age -= 1;
      }

      if (age >= 6) {
        return;
      }

      event.preventDefault();
      const shouldForce = window.confirm(
        "L'élève a moins de 6 ans au 1er octobre. Voulez-vous quand même valider l'inscription ?",
      );
      if (!shouldForce) {
        return;
      }

      let forceInput = studentAddForm.querySelector(
        'input[name="force_underage"]',
      );
      if (!forceInput) {
        forceInput = document.createElement('input');
        forceInput.type = 'hidden';
        forceInput.name = 'force_underage';
        studentAddForm.appendChild(forceInput);
      }
      forceInput.value = '1';
      studentAddForm.submit();
    });
  }

  const initZipCityAutofill = () => {
    const forms = document.querySelectorAll('form');
    forms.forEach((form) => {
      const zipInput = form.querySelector('input[name="zip_code"]');
      const cityInput = form.querySelector('input[name="city"]');
      if (!zipInput || !cityInput) {
        return;
      }

      const datalistId =
        cityInput.getAttribute('list') ||
        `city-suggestions-${Math.random().toString(36).slice(2, 8)}`;
      let datalist = document.getElementById(datalistId);
      if (!datalist) {
        datalist = document.createElement('datalist');
        datalist.id = datalistId;
        form.appendChild(datalist);
      }
      cityInput.setAttribute('list', datalistId);

      const fetchCities = async () => {
        const zip = (zipInput.value || '').trim();
        if (!/^\d{5}$/.test(zip)) {
          return;
        }
        try {
          const response = await fetch(
            `https://geo.api.gouv.fr/communes?codePostal=${zip}&fields=nom&format=json`,
          );
          if (!response.ok) {
            return;
          }
          const cities = await response.json();
          if (!Array.isArray(cities) || cities.length === 0) {
            return;
          }

          datalist.innerHTML = '';
          cities.forEach((city) => {
            const option = document.createElement('option');
            option.value = city.nom;
            datalist.appendChild(option);
          });

          if (!cityInput.value && cities[0] && cities[0].nom) {
            cityInput.value = cities[0].nom;
            triggerFieldEvents(cityInput);
          }
        } catch (_error) {
          // Optional helper only: fail silently if API unavailable.
        }
      };

      zipInput.addEventListener('blur', fetchCities);
      zipInput.addEventListener('change', fetchCities);
    });
  };

  initZipCityAutofill();

  // Hamburger nav toggle
  const burger = document.getElementById('nav-burger');
  const nav = document.getElementById('main-nav');
  if (burger && nav) {
    burger.addEventListener('click', () => {
      const open = nav.classList.toggle('open');
      burger.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }

  // Dropdown menus
  document.querySelectorAll('.nav-dropdown').forEach((dropdown) => {
    const btn = dropdown.querySelector('.nav-drop-btn');
    if (!btn) return;
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const isOpen = dropdown.classList.toggle('open');
      btn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
      // Fermer les autres
      document.querySelectorAll('.nav-dropdown.open').forEach((other) => {
        if (other !== dropdown) {
          other.classList.remove('open');
          other
            .querySelector('.nav-drop-btn')
            ?.setAttribute('aria-expanded', 'false');
        }
      });
    });
  });

  // Clic extérieur ferme les dropdowns
  document.addEventListener('click', () => {
    document.querySelectorAll('.nav-dropdown.open').forEach((d) => {
      d.classList.remove('open');
      d.querySelector('.nav-drop-btn')?.setAttribute('aria-expanded', 'false');
    });
  });

  // Family select type-ahead in student form
  const familySearch = document.getElementById('family-select-search');
  const familySelect = document.getElementById('family-select');
  const newFamilyFields = document.querySelectorAll('[data-new-family-field]');

  const toggleNewFamilyFields = () => {
    if (!familySelect || newFamilyFields.length === 0) {
      return;
    }

    const useExistingFamily = Boolean(familySelect.value);
    newFamilyFields.forEach((field) => {
      field.hidden = useExistingFamily;
      field.style.display = useExistingFamily ? 'none' : '';
      field.querySelectorAll('input, select, textarea').forEach((input) => {
        input.disabled = useExistingFamily;
        if (input.hasAttribute('required')) {
          input.dataset.wasRequired = 'true';
        }
        if (useExistingFamily) {
          input.removeAttribute('required');
        } else if (input.dataset.wasRequired === 'true') {
          input.setAttribute('required', 'required');
        }
      });
    });
  };

  if (familySelect) {
    familySelect.addEventListener('change', toggleNewFamilyFields);
    toggleNewFamilyFields();
  }

  if (familySearch && familySelect) {
    const pickMatch = () => {
      const term = normalizeText(familySearch.value.trim());
      if (!term) {
        toggleNewFamilyFields();
        return;
      }

      const options = Array.from(familySelect.options).filter(
        (option) => option.value,
      );

      const startsWithMatch = options.find((option) =>
        normalizeText(option.textContent).startsWith(term),
      );
      const includesMatch = options.find((option) =>
        normalizeText(option.textContent).includes(term),
      );
      const match = startsWithMatch || includesMatch;

      if (match) {
        familySelect.value = match.value;
      } else {
        familySelect.value = '';
      }

      toggleNewFamilyFields();
    };

    familySearch.addEventListener('input', pickMatch);
    familySearch.addEventListener('change', pickMatch);
  }

  // Suggested amount auto-fill on payments form
  const paymentFamilySelect = document.getElementById('payment-family-select');
  const paymentTotalAmount = document.getElementById('payment-total-amount');
  if (paymentFamilySelect && paymentTotalAmount) {
    const applySuggestedAmount = (force = false) => {
      const option = paymentFamilySelect.selectedOptions[0];
      if (!option) {
        return;
      }

      const suggested = Number.parseFloat(option.dataset.suggested || '');
      if (!Number.isFinite(suggested)) {
        return;
      }

      const shouldFill =
        force ||
        !paymentTotalAmount.value ||
        paymentTotalAmount.dataset.autofilled === '1';

      if (shouldFill) {
        paymentTotalAmount.value = suggested.toFixed(2);
        paymentTotalAmount.dataset.autofilled = '1';
      }
    };

    paymentFamilySelect.addEventListener('change', () =>
      applySuggestedAmount(true),
    );
    paymentTotalAmount.addEventListener('input', () => {
      paymentTotalAmount.dataset.autofilled = '0';
    });

    applySuggestedAmount(false);
  }

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
