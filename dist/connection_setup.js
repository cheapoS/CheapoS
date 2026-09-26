(function(root){
'use strict';
// Setup text is data. This parser does not fetch links, execute examples, or infer access.
function parse(text){
 text=String(text||'').slice(0,20000);
 const candidates=[];
 const pattern=/(?:https?:\/\/)?(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}(?::\d+)?(?:\/[^\s<>"'`\[\]()*,\\]*)?/gi;
 for(const match of text.matchAll(pattern)){
  let raw=match[0].replace(/[.;!?]+$/,'');
  try{
   const url=new URL(/^https?:\/\//i.test(raw)?raw:'https://'+raw);
   if(url.username||url.password||url.search||url.hash||url.hostname==='t.co')continue;
   const before=text.slice(Math.max(0,match.index-35),match.index);
   if(!/\/v\d+(?:\/|$)/i.test(url.pathname)&&!/base[_\s-]*(?:url|uri)|api\s*(?:url|endpoint)\s*[:=]?\s*["'`]?$/i.test(before))continue;
   url.pathname=url.pathname.replace(/\/(chat\/completions|responses|models)\/?$/,'').replace(/\/$/,'');
   const base=url.toString().replace(/\/$/,'');
   if(!candidates.includes(base))candidates.push(base);
  }catch(_){}
 }
 const ids=[];
 for(const match of text.matchAll(/(?:["']model["']\s*:\s*|\bmodel\s*=\s*|\bmodel\s+id\s*:\s*)["'`]([a-zA-Z0-9][a-zA-Z0-9_./:\-]{0,199})["'`]/gi))if(!ids.includes(match[1]))ids.push(match[1]);
 const base_url=candidates.length===1?candidates[0]:'';
 return {base_url,name:base_url?new URL(base_url).hostname.replace(/^api\./,''):'',model:ids.length===1?ids[0]:'',candidates,
  message:candidates.length>1?'Several API addresses found. Choose one connection below.':base_url?'Review the extracted address. Model names and free-access claims still need verification.':'No explicit API address found. Enter the API base URL from the provider’s documentation.'};
}
const api={parse};if(typeof module!=='undefined'&&module.exports)module.exports=api;root.CheapOSConnectionSetup=api;
})(typeof globalThis!=='undefined'?globalThis:this);
