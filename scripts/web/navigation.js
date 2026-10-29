/* Shared by judgment and cluster viewers. All reader state lives in the URL. */
(() => {
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const refs = new Map();
  let sequence = 0, trigger = null;
  const pane = document.createElement('aside');
  pane.className = 'source-pane'; pane.hidden = true; pane.setAttribute('aria-label', '原文の本文表示');
  pane.innerHTML = '<div class="source-pane-toolbar"><strong></strong><a target="_blank" rel="noopener">別タブで開く</a><button type="button">閉じる</button></div><iframe title="対象箇所の原文"></iframe>';
  document.body.append(pane);
  function url(ref) {
    const u = new URL(ref.url, location.href);
    const state = new URLSearchParams();
    ref.ids.forEach(id => state.append('id', id));
    (ref.quotes || []).forEach(q => state.append('q', q));
    u.hash = state.toString(); return u.href;
  }
  function close() {
    pane.hidden = true; document.body.classList.remove('reader-open');
    trigger?.focus(); window.dispatchEvent(new Event('resize'));
  }
  function open(ref, button) {
    trigger = button; pane.hidden = false; document.body.classList.add('reader-open');
    pane.querySelector('strong').textContent = ref.title;
    pane.querySelector('a').href = url(ref);
    pane.querySelector('iframe').src = url(ref);
    pane.querySelector('button').focus(); window.dispatchEvent(new Event('resize'));
  }
  pane.querySelector('button').onclick = close;
  document.addEventListener('keydown', e => {if(e.key === 'Escape' && !pane.hidden) close();});
  document.addEventListener('click', e => {
    const button = e.target.closest('[data-source-ref]');
    if(button && refs.has(button.dataset.sourceRef)) open(refs.get(button.dataset.sourceRef), button);
  });
  window.SourceNavigation = {
    actions(ref, label = '本文を表示') {
      if(!ref) return '';
      const id = String(++sequence); refs.set(id, ref);
      return `<div class="ref-actions"><button type="button" data-source-ref="${id}">${esc(label)}</button><a href="${esc(url(ref))}" target="_blank" rel="noopener">別タブで開く ↗</a></div>`;
    },
    reset() {refs.clear();}, url, open, close
  };
})();
