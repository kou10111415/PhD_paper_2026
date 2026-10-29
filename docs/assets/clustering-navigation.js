(() => {
  const sources=JSON.parse(document.getElementById('source-navigation').textContent);
  const N=window.SourceNavigation,host=document.createElement('section');
  host.className='cluster-request';host.setAttribute('aria-live','polite');
  host.innerHTML='<h2>要求の本文を確認</h2><p>散布図の点をクリックすると、要求と議事録へのリンクを表示します。</p>';
  document.querySelector('.layout').after(host);
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const plot=document.getElementById('scatter');
  plot.on('plotly_click',event=>{
    const clicked=event.points[0];if(!clicked)return;
    const pts=filtered(),key=document.getElementById('level').value+'_cluster_id';
    const cid=clicked.data.name.split(' ')[0];
    const members=pts.filter(r=>r[key]===cid),r=members[clicked.pointIndex ?? clicked.pointNumber];
    if(!r)return;
    host.innerHTML=`<h2>${esc(r.request_summary)}</h2><p class="meta">${esc(r.request_id)} · ${esc(r.speaker_or_heading)}</p>${N.actions(sources[r.request_id],'議事録・原資料を表示')}<p><a href="judgments.html?request=${encodeURIComponent(r.request_id)}" target="_blank" rel="noopener">この要求の改訂判定を開く ↗</a></p><details><summary>発言・意見全文</summary><p class="request">${esc(r.original_text)}</p></details>`;
    host.scrollIntoView({block:'center',behavior:'smooth'});
  });
})();
