/* Local layout preferences only; no task or execution state. */
(function(root){
  const limits=(side,viewport)=>{
    const max=Math.max(0,Math.floor(viewport<=700?Math.min(360,viewport-32):viewport*(side==='left'?.285:.25)));
    return {min:Math.min(max,side==='left'?180:220),max};
  };
  function settledWidth(width,side,viewport){
    const {min,max}=limits(side,viewport);
    return width<=56?0:Math.round(Math.min(max,Math.max(min,width)));
  }
  function mount(){
    const key='cheapos-panel-layout-v1',panels={left:document.querySelector('#sidebar'),right:document.querySelector('#inspector')};
    let saved={};try{saved=JSON.parse(localStorage.getItem(key))||{}}catch{}
    const layout={};
    for(const side of ['left','right']){
      const item=saved[side]||{},fallback=side==='left'?238:340;
      layout[side]={width:Number.isFinite(item.width)&&item.width>56?item.width:fallback,open:typeof item.open==='boolean'?item.open:side==='left'&&innerWidth>700};
    }
    let dragging=null,mobile=innerWidth<=700;
    if(mobile&&layout.left.open&&layout.right.open)layout.left.open=false;
    const persist=()=>{try{localStorage.setItem(key,JSON.stringify(layout))}catch{}};
    function paint(){
      document.body.classList.add('resizable-panels');
      document.documentElement.style.setProperty('--panel-top',document.querySelector('.topbar').getBoundingClientRect().bottom+'px');
      for(const side of ['left','right']){
        const panel=panels[side],item=layout[side],handle=panel.querySelector('.panel-resizer');
        const width=dragging?.side===side?Math.max(1,Math.min(limits(side,innerWidth).max,dragging.width)):settledWidth(item.width,side,innerWidth);
        panel.style.width=width+'px';
        panel.classList.toggle('collapsed',!item.open);
        panel.classList.toggle('hidden',!item.open);
        panel.classList.toggle('show',item.open);
        handle.setAttribute('aria-valuenow',item.open?Math.round(width):0);
        handle.setAttribute('aria-valuemax',limits(side,innerWidth).max);
      }
      const leftButton=document.querySelector('#mobile-menu'),rightButton=document.querySelector('#toggle-inspector');
      leftButton.style.display='flex';
      leftButton.setAttribute('aria-expanded',layout.left.open);
      leftButton.setAttribute('aria-label',layout.left.open?'Hide sidebar':'Show sidebar');
      rightButton.setAttribute('aria-expanded',layout.right.open);
      rightButton.setAttribute('aria-label',layout.right.open?'Hide session details':'Show session details');
    }
    function show(side,open){
      layout[side].open=open;
      if(open&&innerWidth<=700)layout[side==='left'?'right':'left'].open=false;
      paint();persist();
    }
    function finish(cancel=false){
      if(!dragging)return;
      const {side,width,handle,pointerId}=dragging;
      dragging=null;
      document.body.classList.remove('resizing-panels');
      if(handle.hasPointerCapture(pointerId))handle.releasePointerCapture(pointerId);
      if(!cancel){
        const settled=settledWidth(width,side,innerWidth);
        if(settled)layout[side].width=settled;
        layout[side].open=settled>0;
      }
      paint();persist();
      if(!layout[side].open)document.querySelector(side==='left'?'#mobile-menu':'#toggle-inspector').focus();
    }
    for(const side of ['left','right']){
      const panel=panels[side],handle=panel.querySelector('.panel-resizer');
      handle.addEventListener('pointerdown',event=>{
        if(event.button!==0||dragging)return;
        event.preventDefault();
        dragging={side,handle,pointerId:event.pointerId,start:event.clientX,initial:panel.getBoundingClientRect().width,width:panel.getBoundingClientRect().width};
        handle.setPointerCapture(event.pointerId);
        document.body.classList.add('resizing-panels');
      });
      handle.addEventListener('pointermove',event=>{
        if(!dragging||dragging.pointerId!==event.pointerId)return;
        dragging.width=dragging.initial+(event.clientX-dragging.start)*(side==='left'?1:-1);
        paint();
      });
      handle.addEventListener('pointerup',()=>finish());
      handle.addEventListener('pointercancel',()=>finish(true));
      handle.addEventListener('lostpointercapture',()=>finish(true));
      handle.addEventListener('keydown',event=>{
        if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
        event.preventDefault();
        let width=panel.getBoundingClientRect().width;
        width=event.key==='Home'?0:event.key==='End'?limits(side,innerWidth).max:width+(event.key==='ArrowRight'?1:-1)*(side==='left'?1:-1)*(event.shiftKey?50:20);
        // Crossing the minimum with a keyboard step collapses the panel.
        const settled=width<limits(side,innerWidth).min?0:settledWidth(width,side,innerWidth);
        if(settled)layout[side].width=settled;
        show(side,settled>0);
        if(!settled)document.querySelector(side==='left'?'#mobile-menu':'#toggle-inspector').focus();
      });
    }
    document.querySelector('#sidebar-toggle').onclick=()=>show('left',false);
    document.querySelector('#mobile-menu').onclick=()=>show('left',!layout.left.open);
    document.querySelector('#toggle-inspector').onclick=()=>show('right',!layout.right.open);
    document.querySelector('#compact-session').onclick=()=>show('right',!layout.right.open);
    document.addEventListener('keydown',event=>{
      if(event.key!=='Escape')return;
      if(dragging){finish(true);return}
      if(innerWidth<=700&&!document.querySelector('dialog[open]')){layout.left.open=false;layout.right.open=false;paint();persist()}
    });
    window.addEventListener('resize',()=>{
      if(dragging)finish(true);
      const narrow=innerWidth<=700;
      if(narrow&&!mobile){layout.left.open=false;layout.right.open=false}
      mobile=narrow;paint();
    });
    paint();
    return {closeMobileSidebar:()=>{if(innerWidth<=700)show("left",false)}};
  }
  const api={limits,settledWidth,mount};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  else root.CheapOSPanels=api;
})(typeof globalThis!=='undefined'?globalThis:this);
