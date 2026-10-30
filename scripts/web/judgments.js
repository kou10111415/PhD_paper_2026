(() => {
  const all=JSON.parse(document.getElementById('data').textContent),N=window.SourceNavigation;
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const mode=r=>r.judgment_mode==='not_evaluated'?'未判定':r.judgment_mode==='single_document_presence'?'単一文書の記載有無':'新旧比較';
  const stage=r=>r.old_document_label?`${r.old_document_label} → ${r.new_document_label}`:r.new_document_label||r.stage||'';
  const human=r=>(r.manual_search||{}).status==='found'?'該当あり':(r.manual_search||{}).status==='not_found'?'該当なし':'';
  const fields={mode,stage,source:r=>r.source_group,judgment:r=>r.final_judgment_label_ja,llm:r=>r.judgment,manual:human};
  let page=0;const size=20;
  for(const [id,value] of Object.entries(fields)) {
    const el=document.getElementById(id);el.add(new Option('すべて',''));
    const options=id==='judgment'
      ? ['対応あり','一部対応','対応なし','判定不可',...(all.some(r=>r.final_judgment==='not_evaluated')?['未判定']:[])]
      : [...new Set(all.map(value).filter(Boolean))];
    options.forEach(v=>el.add(new Option(v,v)));
    el.onchange=()=>{page=0;render();};
  }
  const search=document.getElementById('search');
  search.value=new URLSearchParams(location.search).get('request')||'';
  search.oninput=()=>{page=0;render();};
  function filtered() {
    const q=search.value.trim().toLowerCase();
    return all.filter(r=>Object.entries(fields).every(([id,value])=>!document.getElementById(id).value||document.getElementById(id).value===value(r))&&(!q||[r.request_id,r.request_summary,r.original_text_display,r.request_quote,r.reason,...(r.matched_revisions||[]).map(v=>[v.alignment_id,...(v.old||[]),...(v.new||[])].join(' '))].join(' ').toLowerCase().includes(q)));
  }
  function quotes(r,aid) {
    const evidence=(r.evidence||[]).filter(e=>e.alignment_id===aid);
    const single=(r.document_evidence_quotes||[]).filter(e=>e.alignment_id===aid);
    const content=single.map(e=>`<p class="quote">${esc(e.quote)}</p><p>${esc(e.reason)}</p>`).join('')+evidence.map(e=>`${e.old_evidence_quote?`<p class="quote"><b>旧版の引用</b> ${esc(e.old_evidence_quote)}</p>`:''}${e.new_evidence_quote?`<p class="quote"><b>新版の引用</b> ${esc(e.new_evidence_quote)}</p>`:''}<p>${esc(e.reason)}</p>`).join('');
    return content?`<details><summary>根拠引用と説明</summary>${content}</details>`:'';
  }
  function diffMarkup(text) {
    return esc(text||'').replace(/\[\+([\s\S]*?)\+\]/g,'<ins>$1</ins>').replace(/\[-([\s\S]*?)-\]/g,'<del>$1</del>');
  }
  function revision(r,v,index,manual=false) {
    const presence=r.judgment_mode==='single_document_presence';
    const different=(v.old_text||'')!==(v.new_text||'');
    const old=presence?'':`<section class="panel"><b>${esc(r.old_document_label||'旧版')} · ${esc((v.old||[]).join(', '))}</b>${N.actions(v.old_ref,'旧版の本文を表示')}<div>${esc(v.old_text||'対応記載なし')}</div></section>`;
    return `<section class="rev"><h3>${manual?'人手確認箇所':presence?'記載箇所':'対応改訂'} ${index+1} · ${esc(v.alignment_id)}</h3><p class="meta">${esc(v.element_type)} · ${esc(v.relation)} · ${esc(v.section_heading)}</p><div class="${presence?'':'pair'}">${old}<section class="panel"><b>${esc(r.new_document_label||'本文')} · ${esc((v.new||[]).join(', '))}</b>${N.actions(v.new_ref,presence?'本文を表示':'新版の本文を表示')}<div>${esc(v.new_text||'対応記載なし')}</div></section></div>${!presence?`<section class="diff-panel"><h4>差分ハイライト</h4>${different?`<div class="panel">${diffMarkup(v.inline_diff)}</div>`:'<p class="meta">本文の変更はありません。</p>'}</section>`:''}${quotes(r,v.alignment_id)}${v.selection_reason?`<p>${esc(v.selection_reason)}</p>`:''}</section>`;
  }
  function card(r) {
    const notEvaluated=r.judgment==='not_evaluated';
    return `<article class="card" data-request-id="${esc(r.request_id)}"><div><span class="badge">${esc(r.source_group)}</span><span class="badge">${esc(mode(r))}</span><span class="badge">${esc(stage(r))}</span><span class="badge display-judgment">表示判定：${esc(r.final_judgment_label_ja)}</span>${!notEvaluated?`<span class="badge">LLM：${esc(r.judgment)}</span>`:''}${human(r)?`<span class="badge">人手探索：${esc(human(r))}</span>`:''}</div><h2>${esc(r.request_summary)}</h2><p class="meta">${esc(r.request_id)} · ${esc(r.speaker_display)}</p>${r.judgment_mode==='single_document_presence'?'<p class="notice">単一文書への記載有無です。改訂や意見の採用を示すものではありません。</p>':''}${notEvaluated?'<p class="notice">保存済みの判定結果がありません。「対応なし」とは区別しています。</p>':''}<p class="request"><b>要求原文：</b>${esc(r.request_quote||r.original_text_display)}</p>${N.actions(r.source_ref,'議事録・原資料を表示')}<p class="reason"><b>${notEvaluated?'収録状況':'LLM判定理由'}：</b>${esc(r.reason)}</p>${(r.matched_revisions||[]).map((v,i)=>revision(r,v,i)).join('')}${(r.additional_evidence||[]).length?`<details><summary>その他の参照引用</summary>${r.additional_evidence.map(e=>`<p class="quote">${esc(e.quote)}</p><p>${esc(e.reason)}</p>${N.actions(e.ref,'参照本文を表示')}`).join('')}</details>`:''}${!(r.matched_revisions||[]).length&&!notEvaluated?'<p class="meta">判定結果に対応箇所の指定がありません。</p>':''}<details><summary>発言・意見全文と参考情報</summary><p class="request">${esc(r.original_text_display)}</p>${r.opinion_heading_reference||r.label?`<p>${esc(r.opinion_heading_reference||r.label)}</p>`:''}${r.reply||r.administrative_reply_reference?`<p class="request"><b>行政回答：</b>${esc(r.reply||r.administrative_reply_reference)}</p>`:''}</details></article>`;
  }
  function render() {
    N.reset();const rows=filtered(),pages=Math.max(1,Math.ceil(rows.length/size));page=Math.min(page,pages-1);
    document.getElementById('summary').textContent=`表示 ${rows.length.toLocaleString()} / 全${all.length.toLocaleString()}要求（保存済み判定 ${all.filter(r=>r.judgment!=='not_evaluated').length.toLocaleString()}・未判定 ${all.filter(r=>r.judgment==='not_evaluated').length}）`;
    document.getElementById('cards').innerHTML=rows.length?rows.slice(page*size,(page+1)*size).map(card).join(''):'<p class="empty">条件に一致する要求がありません。</p>';
    document.getElementById('page').textContent=`${page+1} / ${pages}`;
    document.getElementById('prev').disabled=page===0;document.getElementById('next').disabled=page>=pages-1;
  }
  document.getElementById('prev').onclick=()=>{page--;render();window.scrollTo(0,0);};
  document.getElementById('next').onclick=()=>{page++;render();window.scrollTo(0,0);};
  render();window.judgmentViewer={all,filtered};
})();
