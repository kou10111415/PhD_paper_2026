(() => {
  // Index original UTF-16 positions so normalized matches highlight original text.
  function indexed(text) {
    let normalized = '', positions = [];
    for(let i=0; i<text.length;) {
      const ch = String.fromCodePoint(text.codePointAt(i)), end = i + ch.length;
      for(const n of ch.normalize('NFKC')) if(!/\s/u.test(n)) {
        normalized += n;
        for(let j=0;j<n.length;j++) positions.push([i,end]);
      }
      i=end;
    }
    return {normalized, positions};
  }
  const normalize = text => indexed(text).normalized;
  function highlight(block, quotes) {
    const text = block.textContent, {normalized,positions} = indexed(text), ranges=[];
    for(const quote of quotes) {
      const q = normalize(quote); if(!q) continue;
      let start = 0, at;
      while((at=normalized.indexOf(q,start)) >= 0) {
        ranges.push([positions[at][0],positions[at+q.length-1][1]]); start=at+q.length;
      }
    }
    ranges.sort((a,b)=>a[0]-b[0]);
    const merged=[];
    for(const r of ranges) {
      const prev=merged.at(-1); if(prev && r[0]<=prev[1]) prev[1]=Math.max(prev[1],r[1]); else merged.push([...r]);
    }
    if(!merged.length) return 0;
    const fragment=document.createDocumentFragment();let end=0;
    for(const [a,b] of merged) {
      fragment.append(document.createTextNode(text.slice(end,a)));
      const mark=document.createElement('mark');mark.textContent=text.slice(a,b);fragment.append(mark);end=b;
    }
    fragment.append(document.createTextNode(text.slice(end)));block.replaceChildren(fragment);
    return merged.length;
  }
  function navigate() {
    document.querySelectorAll('.source-text,h2').forEach(e=>{if(e.querySelector('mark')) e.textContent=e.textContent;});
    document.querySelectorAll('.target').forEach(e=>e.classList.remove('target'));
    const params=new URLSearchParams(location.hash.slice(1));
    const ids=params.getAll('id'),quotes=params.getAll('q');
    const found=[],missing=[]; let count=0;
    for(const id of ids) {
      const el=document.getElementById(id);
      if(!el || !el.classList.contains('source-block')) {missing.push(id);continue;}
      el.classList.add('target');found.push(el);
      const content=el.querySelector('.source-text,h2');
      if(content)count+=highlight(content,quotes);
    }
    const status=document.getElementById('reader-status');
    status.textContent=missing.length?`該当IDを確認できません：${missing.join(', ')}`:ids.length?`対象 ${found.length}箇所${count?`・引用 ${count}箇所を強調表示`:quotes.length?'・引用の完全一致がないため段落のみ強調表示':'を強調表示'}`:'本文全文を表示しています。';
    const nav=document.getElementById('target-nav');nav.replaceChildren();
    found.forEach(el=>{const a=document.createElement('a');a.href='#'+new URLSearchParams([['id',el.id],...quotes.map(q=>['q',q])]).toString();a.textContent=el.id;a.onclick=e=>{e.preventDefault();el.scrollIntoView({block:'center',behavior:'smooth'});};nav.append(a);});
    requestAnimationFrame(()=>found[0]?.scrollIntoView({block:'center'}));
    // Exposed as diagnostics for the regression suite, no private state.
    window.readerResult={ids,found:found.length,missing,highlights:count};
  }
  document.getElementById('copy-link').onclick=async e=>{
    try{await navigator.clipboard.writeText(location.href);e.target.textContent='コピーしました';}
    catch{document.getElementById('reader-status').textContent='アドレスバーのURLをコピーしてください。';}
  };
  window.addEventListener('hashchange',navigate);navigate();
})();
