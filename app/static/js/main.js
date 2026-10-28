document.addEventListener('DOMContentLoaded', () => {
  const normalizeText = (value) =>
    (value || '')
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '');

  const injectCsrfTokens = () => {
    const meta = document.querySelector('meta[name="csrf-token"]');
    const token = meta ? meta.getAttribute('content') : '';
    if (!token) {
      return;
    }
    document.querySelectorAll('form').forEach((form) => {
      const method = (form.getAttribute('method') || 'get').toLowerCase();
      if (method !== 'post') {
        return;
      }
      if (form.querySelector('input[name="csrf_token"]')) {
        return;
      }
      const input = document.createElement('input');
      input.type = 'hidden';
      input.name = 'csrf_token';
      input.value = token;
      form.prepend(input);
    });
  };
  injectCsrfTokens();

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

  const initFrenchDatePickers = (scope = document) => {
    if (typeof flatpickr === 'undefined') {
      return;
    }

    const fields = scope.querySelectorAll(
      'input.fr-date-input, input[type="date"], input.calendar-fr',
    );

    fields.forEach((field) => {
      if (field.dataset.flatpickrReady === '1') {
        return;
      }

      const fieldType = (field.getAttribute('type') || '').toLowerCase();
      if (fieldType === 'date') {
        field.setAttribute('type', 'text');
      }

      if (!field.placeholder) {
        field.placeholder = 'JJ-MM-AAAA';
      }
      if (!field.getAttribute('pattern')) {
        field.setAttribute('pattern', '^\\d{2}[-/]\\d{2}[-/]\\d{4}$');
      }

      flatpickr(field, {
        locale:
          typeof flatpickr.l10ns !== 'undefined' && flatpickr.l10ns.fr
            ? flatpickr.l10ns.fr
            : 'fr',
        dateFormat: 'd-m-Y',
        allowInput: true,
        clickOpens: true,
        disableMobile: true,
      });

      field.dataset.flatpickrReady = '1';
    });
  };

  const formatBirthDateInput = (rawValue) => {
    const digits = (rawValue || '').replace(/\D/g, '').slice(0, 8);
    if (digits.length <= 2) {
      return digits;
    }
    if (digits.length <= 4) {
      return `${digits.slice(0, 2)}-${digits.slice(2)}`;
    }
    return `${digits.slice(0, 2)}-${digits.slice(2, 4)}-${digits.slice(4)}`;
  };

  const initBirthDateMask = () => {
    document
      .querySelectorAll('input.fr-date-input, input[name="birth_date"]')
      .forEach((field) => {
        if (field.dataset.flatpickrReady === '1') {
          return;
        }
        if ((field.getAttribute('type') || '').toLowerCase() === 'date') {
          return;
        }
        if (field.dataset.birthDateMaskReady === '1') {
          return;
        }

        const applyMask = () => {
          const formatted = formatBirthDateInput(field.value);
          if (field.value !== formatted) {
            field.value = formatted;
          }
        };

        field.addEventListener('input', applyMask);
        field.addEventListener('paste', () => {
          window.setTimeout(applyMask, 0);
        });
        field.addEventListener('blur', applyMask);
        field.dataset.birthDateMaskReady = '1';
        applyMask();
      });
  };

  initAutoToggleForms();
  initFrenchDatePickers();
  initBirthDateMask();

  // Native date pickers use browser locale; enforce French hints consistently.
  document.querySelectorAll('input[type="date"]').forEach((field) => {
    if (!field.getAttribute('lang')) {
      field.setAttribute('lang', 'fr-FR');
    }
  });

  // Initialize time slot handlers for courses
  const TIME_SLOTS = {
    matin: { start: 9, end: 12, start_min: 0, end_min: 15 },
    'après-midi': { start: 13, end: 17, start_min: 45, end_min: 0 },
  };

  const initTimeSlots = () => {
    const timeSlotSelects = document.querySelectorAll('.time-slot-select');
    timeSlotSelects.forEach((select) => {
      const form = select.closest('form');
      if (!form) return;

      const startTimeInput = form.querySelector('.start-time-input');
      const endTimeInput = form.querySelector('.end-time-input');
      const startHourInput = form.querySelector('.start-hour-input');
      const endHourInput = form.querySelector('.end-hour-input');

      if (!startTimeInput || !endTimeInput) return;

      const updateTimes = () => {
        const slot = TIME_SLOTS[select.value];
        if (slot) {
          const startTime = `${String(slot.start).padStart(2, '0')}:${String(slot.start_min).padStart(2, '0')}`;
          const endTime = `${String(slot.end).padStart(2, '0')}:${String(slot.end_min).padStart(2, '0')}`;
          startTimeInput.value = startTime;
          endTimeInput.value = endTime;
          if (startHourInput) startHourInput.value = slot.start;
          if (endHourInput) endHourInput.value = slot.end;
        }
      };

      // Initialize from existing values on page load
      const initFromExisting = () => {
        if (startHourInput && startHourInput.value) {
          const sh = parseInt(startHourInput.value);
          if (sh >= 0 && sh <= 23) {
            startTimeInput.value = `${String(sh).padStart(2, '0')}:00`;
          }
        }
        if (endHourInput && endHourInput.value) {
          const eh = parseInt(endHourInput.value);
          if (eh >= 0 && eh <= 23) {
            endTimeInput.value = `${String(eh).padStart(2, '0')}:00`;
          }
        }
      };

      initFromExisting();

      select.addEventListener('change', updateTimes);

      // Handle time input changes - sync to hidden fields
      const syncToHidden = (timeInput, hourInput) => {
        timeInput.addEventListener('change', () => {
          const [h] = timeInput.value.split(':');
          if (hourInput && h) hourInput.value = parseInt(h);
        });
      };

      syncToHidden(startTimeInput, startHourInput);
      syncToHidden(endTimeInput, endHourInput);
    });
  };

  initTimeSlots();

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

  const initAutocompleteHints = () => {
    const autocompleteByName = {
      first_name: 'given-name',
      last_name: 'family-name',
      email: 'email',
      password: 'new-password',
      birth_date: 'bday',
      phone_number: 'tel',
      father_phone: 'tel',
      mother_phone: 'tel',
      street: 'street-address',
      address: 'street-address',
      city: 'address-level2',
      zip_code: 'postal-code',
      school_year: 'off',
      title: 'organization-title',
      description: 'off',
      room: 'off',
    };

    document
      .querySelectorAll('input[name], textarea[name], select[name]')
      .forEach((field) => {
        const fieldName = field.getAttribute('name');
        if (!fieldName || field.hasAttribute('autocomplete')) {
          return;
        }

        const autocomplete = autocompleteByName[fieldName];
        if (autocomplete) {
          field.setAttribute('autocomplete', autocomplete);
        }
      });
  };

  initAutocompleteHints();

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
  const paymentCreationMode = document.getElementById('payment-creation-mode');
  const paymentMethodSelect = document.getElementById('payment-method-select');
  const customMethodWrapper = document.getElementById('custom-method-wrapper');
  const customMethodInput = document.getElementById('custom-method-input');
  const familyRemainingDisplay = document.getElementById(
    'family-remaining-display',
  );
  const paymentCreationAlert = document.getElementById(
    'payment-creation-alert',
  );
  const paymentCreateForm = document.getElementById('payment-create-form');
  const paymentCreateSubmit = document.getElementById('payment-create-submit');

  if (paymentMethodSelect && customMethodWrapper && customMethodInput) {
    const toggleCustomMethod = () => {
      const isCustom = paymentMethodSelect.value === 'MANUAL';
      customMethodWrapper.style.display = isCustom ? '' : 'none';
      customMethodInput.required = isCustom;
      if (!isCustom) {
        customMethodInput.value = '';
      }
    };
    paymentMethodSelect.addEventListener('change', toggleCustomMethod);
    toggleCustomMethod();
  }

  if (paymentFamilySelect && paymentTotalAmount) {
    let lastRemaining = Number.NaN;
    let lastActiveChildren = Number.NaN;

    const setCreationAlert = (message = '', level = 'warning') => {
      if (!paymentCreationAlert) {
        return;
      }
      if (!message) {
        paymentCreationAlert.style.display = 'none';
        paymentCreationAlert.textContent = '';
        paymentCreationAlert.classList.remove('flash-warning', 'flash-info');
        paymentCreationAlert.classList.add('flash-warning');
        return;
      }
      paymentCreationAlert.textContent = message;
      paymentCreationAlert.style.display = '';
      paymentCreationAlert.classList.remove('flash-warning', 'flash-info');
      paymentCreationAlert.classList.add(
        level === 'info' ? 'flash-info' : 'flash-warning',
      );
    };

    const updateCreationGuard = () => {
      const selectedMode = paymentCreationMode
        ? paymentCreationMode.value
        : 'manual';
      const selectedFamily = paymentFamilySelect.value;
      const isAuto = selectedMode === 'auto';
      let disableSubmit = false;

      if (
        selectedFamily &&
        Number.isFinite(lastActiveChildren) &&
        lastActiveChildren <= 0
      ) {
        setCreationAlert(
          "Création bloquée : cette famille n'a aucun enfant inscrit actif.",
        );
        disableSubmit = true;
      } else if (isAuto && !selectedFamily) {
        setCreationAlert(
          'Sélectionnez une famille pour utiliser le mode Automatique (solde restant).',
        );
        disableSubmit = true;
      } else if (
        isAuto &&
        Number.isFinite(lastRemaining) &&
        lastRemaining <= 0
      ) {
        setCreationAlert(
          'Cette famille est déjà soldée : aucun paiement automatique ne peut être créé. Passez en mode Manuel si nécessaire.',
        );
        disableSubmit = true;
      } else if (isAuto && Number.isFinite(lastRemaining)) {
        setCreationAlert(
          `Mode automatique actif : le montant sera aligné sur le solde restant (${lastRemaining.toFixed(2)} €).`,
          'info',
        );
      } else {
        setCreationAlert('');
      }

      if (paymentCreateSubmit) {
        paymentCreateSubmit.disabled = disableSubmit;
      }
    };

    const applySuggestedAmount = (force = false) => {
      const option = paymentFamilySelect.selectedOptions[0];
      if (!option) {
        lastRemaining = Number.NaN;
        updateCreationGuard();
        return;
      }

      const suggested = Number.parseFloat(option.dataset.suggested || '');
      const remaining = Number.parseFloat(option.dataset.remaining || '');
      const activeChildren = Number.parseInt(
        option.dataset.activeChildren || '',
        10,
      );
      lastRemaining = remaining;
      lastActiveChildren = activeChildren;
      if (!Number.isFinite(suggested)) {
        updateCreationGuard();
        return;
      }

      if (familyRemainingDisplay) {
        familyRemainingDisplay.textContent = Number.isFinite(remaining)
          ? `${remaining.toFixed(2)} €`
          : '—';
      }

      const selectedMode = paymentCreationMode
        ? paymentCreationMode.value
        : 'manual';
      const targetAmount =
        selectedMode === 'auto' && Number.isFinite(remaining)
          ? Math.max(remaining, 0)
          : suggested;

      const shouldFill =
        force ||
        !paymentTotalAmount.value ||
        paymentTotalAmount.dataset.autofilled === '1';

      if (shouldFill) {
        paymentTotalAmount.value = targetAmount.toFixed(2);
        paymentTotalAmount.dataset.autofilled = '1';
      }

      updateCreationGuard();
    };

    paymentFamilySelect.addEventListener('change', () =>
      applySuggestedAmount(true),
    );
    if (paymentCreationMode) {
      paymentCreationMode.addEventListener('change', () =>
        applySuggestedAmount(true),
      );
    }
    paymentTotalAmount.addEventListener('input', () => {
      paymentTotalAmount.dataset.autofilled = '0';
    });

    if (paymentCreateForm) {
      paymentCreateForm.addEventListener('submit', (event) => {
        const selectedMode = paymentCreationMode
          ? paymentCreationMode.value
          : 'manual';
        if (Number.isFinite(lastActiveChildren) && lastActiveChildren <= 0) {
          event.preventDefault();
          setCreationAlert(
            "Création bloquée : cette famille n'a aucun enfant inscrit actif.",
          );
          window.alert(
            "Impossible de créer un paiement : la famille n'a aucun enfant inscrit actif.",
          );
          return;
        }

        if (
          selectedMode === 'auto' &&
          Number.isFinite(lastRemaining) &&
          lastRemaining <= 0
        ) {
          event.preventDefault();
          setCreationAlert(
            'Création bloquée : le solde restant est déjà à 0. Utilisez le mode Manuel si vous devez enregistrer un paiement exceptionnel.',
          );
          window.alert(
            'Cette famille est déjà soldée. Le mode "Solde restant" ne peut pas créer de paiement.',
          );
        }
      });
    }

    applySuggestedAmount(false);
  }

  // Re-apply date picker and mask on dynamically injected date inputs.
  const observer = new MutationObserver((mutations) => {
    let shouldRefresh = false;
    mutations.forEach((mutation) => {
      mutation.addedNodes.forEach((node) => {
        if (!(node instanceof HTMLElement)) {
          return;
        }
        if (
          node.matches(
            'input.fr-date-input, input[type="date"], input.calendar-fr',
          ) ||
          node.querySelector(
            'input.fr-date-input, input[type="date"], input.calendar-fr',
          )
        ) {
          shouldRefresh = true;
        }
      });
    });

    if (shouldRefresh) {
      initFrenchDatePickers();
      initBirthDateMask();
    }
  });

  observer.observe(document.body, { childList: true, subtree: true });

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
