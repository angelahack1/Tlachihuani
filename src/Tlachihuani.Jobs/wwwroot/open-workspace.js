'use strict';
(async () => {
  const hint = document.getElementById('hint');
  try {
    const response = await fetch('/controllers', {cache:'no-store'});
    if (!response.ok) throw new Error();
    const apps = await response.json();
    if (apps.length === 1) { location.replace(apps[0].url); return; }
    hint.textContent = apps.length ? 'Choose the Tlamatini session whose queue you want to open.' :
      'Open Tlamatini and choose Panels → Torrenter Workspace. Sign in to Tlamatini if prompted.';
    for (const app of apps) {
      const link = document.createElement('a'); link.href=app.url; link.textContent=app.name;
      document.getElementById('apps').append(link);
    }
  } catch { hint.textContent='Open Torrenter Workspace from the Panels menu in Tlamatini.'; }
})();
