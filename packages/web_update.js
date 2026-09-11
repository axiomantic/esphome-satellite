(function() {
  function initUpdateBanner() {
    if (document.getElementById('satellite-ota-banner')) return;

    fetch('/update/firmware')
      .then(function(res) {
        if (!res.ok) return null;
        return res.json();
      })
      .then(function(data) {
        if (!data) return;
        renderBanner(data);
      })
      .catch(function() {});
  }

  function renderBanner(data) {
    if (document.getElementById('satellite-ota-banner')) return;

    var isAvailable = (data.state === 'UPDATE AVAILABLE' || data.state === 'ON');
    var latestVersion = data.value || '';

    var banner = document.createElement('div');
    banner.id = 'satellite-ota-banner';
    banner.style.cssText = 'margin: 16px; padding: 16px 20px; border-radius: 12px; font-family: system-ui, -apple-system, sans-serif; display: flex; align-items: center; justify-content: space-between; gap: 16px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); transition: all 0.3s ease;';

    if (isAvailable) {
      banner.style.background = '#1e293b';
      banner.style.border = '1px solid #3b82f6';
      banner.style.color = '#f8fafc';
      banner.innerHTML = '<div style="flex: 1;">' +
        '<div style="font-weight: 600; font-size: 15px; display: flex; align-items: center; gap: 8px;">' +
          '<span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:#3b82f6;"></span>' +
          'Firmware Update Available' +
        '</div>' +
        '<div style="font-size: 13px; color: #94a3b8; margin-top: 4px;">' +
          'Remote firmware version: <strong style="color: #60a5fa;">' + latestVersion + '</strong>' +
        '</div>' +
      '</div>' +
      '<div>' +
        '<button id="ota-install-btn" style="background: #2563eb; color: #fff; border: none; padding: 8px 18px; border-radius: 8px; font-weight: 500; font-size: 13px; cursor: pointer; transition: background 0.2s;">' +
          'Install OTA Update' +
        '</button>' +
      '</div>';
    } else {
      banner.style.background = 'rgba(255,255,255,0.05)';
      banner.style.border = '1px solid rgba(255,255,255,0.1)';
      banner.style.color = 'inherit';
      banner.innerHTML = '<div style="flex: 1;">' +
        '<div style="font-weight: 500; font-size: 13px; opacity: 0.85;">' +
          'Firmware is up to date (' + (latestVersion || 'latest') + ')' +
        '</div>' +
      '</div>' +
      '<div>' +
        '<button id="ota-install-btn" style="background: transparent; border: 1px solid rgba(128,128,128,0.3); color: inherit; padding: 6px 14px; border-radius: 6px; font-size: 12px; cursor: pointer;">' +
          'Re-flash Remote Firmware' +
        '</button>' +
      '</div>';
    }

    var app = document.querySelector('esp-app') || document.body;
    if (app.firstChild) {
      app.insertBefore(banner, app.firstChild);
    } else {
      app.appendChild(banner);
    }

    var btn = document.getElementById('ota-install-btn');
    if (btn) {
      btn.onclick = function() {
        var msg = isAvailable
          ? 'Initiate remote OTA firmware update now? The satellite will reboot automatically upon completion.'
          : 'Re-flash remote firmware from GitHub now? The satellite will reboot automatically upon completion.';
        if (!confirm(msg)) {
          return;
        }

        btn.disabled = true;
        btn.textContent = 'Starting OTA update...';
        btn.style.background = '#64748b';
        btn.style.cursor = 'wait';

        function startPoll() {
          btn.textContent = 'Flashing firmware... Satellite rebooting soon';
          var countdown = 35;
          var timer = setInterval(function() {
            btn.textContent = 'Rebooting satellite... Reconnecting (' + countdown + 's)';
            countdown--;
            if (countdown <= 0) {
              clearInterval(timer);
              window.location.reload();
            }
          }, 1000);
        }

        fetch('/update/firmware/install', { method: 'POST' })
          .then(function(res) {
            if (res.ok) {
              startPoll();
            } else {
              return fetch('/button/system__update_firmware_to_latest/press', { method: 'POST' })
                .then(function() {
                  startPoll();
                });
            }
          })
          .catch(function() {
            fetch('/button/system__update_firmware_to_latest/press', { method: 'POST' })
              .then(function() {
                startPoll();
              })
              .catch(function() {
                startPoll();
              });
          });
      };
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initUpdateBanner);
  } else {
    initUpdateBanner();
  }
  setTimeout(initUpdateBanner, 1500);
  setTimeout(initUpdateBanner, 4000);
})();
