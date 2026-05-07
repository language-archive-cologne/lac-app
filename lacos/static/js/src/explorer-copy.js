(function () {
  function setSuccessState(button) {
    button.classList.add('text-success');

    var copyIcon = button.querySelector('.copy-icon');
    var checkIcon = button.querySelector('.check-icon');
    if (copyIcon && checkIcon) {
      copyIcon.classList.add('hidden');
      checkIcon.classList.remove('hidden');
    }

    var label = button.querySelector('[data-copy-label]');
    if (label && button.dataset.copySuccessLabel) {
      label.textContent = button.dataset.copySuccessLabel;
    }

    window.setTimeout(function () {
      button.classList.remove('text-success');
      if (copyIcon && checkIcon) {
        copyIcon.classList.remove('hidden');
        checkIcon.classList.add('hidden');
      }
      if (label && button.dataset.copyDefaultLabel) {
        label.textContent = button.dataset.copyDefaultLabel;
      }
    }, 1500);
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }

    var textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.left = '-9999px';
    textarea.style.top = '0';
    document.body.appendChild(textarea);
    textarea.select();

    try {
      document.execCommand('copy');
      return Promise.resolve();
    } catch (error) {
      return Promise.reject(error);
    } finally {
      document.body.removeChild(textarea);
    }
  }

  document.addEventListener('click', function (event) {
    var button = event.target.closest('[data-copy-text]');
    if (!button) return;

    event.preventDefault();
    copyText(button.dataset.copyText || '')
      .then(function () {
        setSuccessState(button);
      })
      .catch(function (error) {
        console.error('[lac-copy]', error);
      });
  });
})();
