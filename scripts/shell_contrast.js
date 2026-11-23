(()=>{
 /* mail 118/119 rendered-contrast scan. WCAG: 4.5:1 for normal text, 3:1 for LARGE text, where
    large = >= 24 CSS px, or >= 18.67 CSS px at bold (>= 700). (119: the first version used
    18.6 px / 14 px bold, which let smaller labels pass at 3:1.)
    MEASURED: every visible text node's parent element, plus the ::before/::after labels of
    elements carrying visible pseudo text (content resolved via getComputedStyle).
    SKIPPED, and COUNTED (never silently): text over a gradient/image background (no single
    background colour), gradient-filled/transparent text, and backgrounds that are only
    translucent all the way up. */
 const cv=document.createElement('canvas');cv.width=cv.height=1;const cx=cv.getContext('2d',{willReadFrequently:true});
 const toRgb=c=>{if(/^rgba?\(/.test(c))return c;cx.clearRect(0,0,1,1);cx.fillStyle='#000';cx.fillStyle=c;cx.fillRect(0,0,1,1);const d=cx.getImageData(0,0,1,1).data;return 'rgb('+d[0]+','+d[1]+','+d[2]+')'};
 const lum=c=>{c=toRgb(c);const a=c.match(/[\d.]+/g).map(Number);const f=v=>{v/=255;return v<=.03928?v/12.92:Math.pow((v+.055)/1.055,2.4)};return .2126*f(a[0])+.7152*f(a[1])+.0722*f(a[2])};
 const skip={bg_image:0,text_fill_transparent:0,translucent_only:0};
 const bgOf=el=>{let e=el;while(e&&e.nodeType===1){const cs=getComputedStyle(e);const b=toRgb(cs.backgroundColor);const m=cs.backgroundColor.match(/[\d.]+/g);
   if(m&&(m.length<4||+m[3]>0.5))return b;if(cs.backgroundImage&&cs.backgroundImage!=='none'&&e.tagName!=='BODY')return 'IMG';e=e.parentElement}
   const bb=getComputedStyle(document.body).backgroundColor;return bb};
 const large=cs=>{const px=parseFloat(cs.fontSize),w=+cs.fontWeight||400;return px>=24||(px>=18.66&&w>=700)};
 const out=[];const seen=new Set();let measured=0,pseudo=0;
 function test(el,cs,txt,kind){
   if((cs.webkitTextFillColor||'').includes('rgba(0, 0, 0, 0)')||cs.color==='rgba(0, 0, 0, 0)'){skip.text_fill_transparent++;return}
   const bg=bgOf(el);if(bg==='IMG'){skip.bg_image++;return}if(!bg){skip.translucent_only++;return}
   const lf=lum(cs.color),lb=lum(bg);const r=(Math.max(lf,lb)+.05)/(Math.min(lf,lb)+.05);measured++;
   if(r<(large(cs)?3:4.5))out.push({t:txt.slice(0,30),r:+r.toFixed(2),px:cs.fontSize,w:cs.fontWeight,c:cs.color,bg,
     sel:kind+el.tagName.toLowerCase()+(el.className&&typeof el.className==='string'?'.'+el.className.split(' ').join('.'):'')+(el.closest('[id]')?' <#'+el.closest('[id]').id:'')});}
 const W=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let n;
 while(n=W.nextNode()){const t=n.textContent.trim();if(t.length<1)continue;const el=n.parentElement;if(!el||seen.has(el))continue;seen.add(el);
  const r=el.getBoundingClientRect();if(!r.width||!r.height||r.bottom<0||r.top>innerHeight*3)continue;
  const cs=getComputedStyle(el);if(cs.visibility==='hidden'||+cs.opacity<.2)continue;test(el,cs,t,'')}
 /* pseudo-element labels: ::before / ::after with string content on visible elements */
 for(const el of document.querySelectorAll('body *')){const r=el.getBoundingClientRect();if(!r.width||!r.height||r.bottom<0||r.top>innerHeight*3)continue;
  for(const ps of ['::before','::after']){const cs=getComputedStyle(el,ps);const c=cs.content;if(!c||c==='none'||c==='normal'||!/^["']|attr\(/.test(c))continue;
   let txt=c.replace(/^["']|["']$/g,'');if(/attr\(([^)]+)\)/.test(c))txt=el.getAttribute(c.match(/attr\(([^)]+)\)/)[1])||'';if(!txt.trim()||cs.display==='none')continue;
   pseudo++;test(el,cs,txt,ps+' ')}}
 const agg={};out.forEach(o=>{const k=o.sel+' | '+o.px+'/'+o.w+' '+o.c+' on '+o.bg;agg[k]=agg[k]||{n:0,ex:o.t,r:o.r};agg[k].n++});
 return {count:out.length,measured,pseudo_measured:pseudo,skipped:skip,groups:Object.entries(agg).sort((a,b)=>b[1].n-a[1].n).slice(0,25)};
})()
