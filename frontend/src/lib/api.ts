const BASE=''
export function token(){return localStorage.getItem('dataready_token')||''}
export async function api<T=any>(path:string,options:RequestInit={}):Promise<T>{
 const headers=new Headers(options.headers); if(token())headers.set('Authorization',`Bearer ${token()}`)
 if(options.body && !(options.body instanceof FormData))headers.set('Content-Type','application/json')
 const res=await fetch(BASE+path,{...options,headers}); if(!res.ok){let message=`Request failed (${res.status})`;try{const body=await res.json();message=body.detail||message}catch{};if(res.status===401){localStorage.removeItem('dataready_token');location.reload()}throw new Error(message)}
 const type=res.headers.get('content-type')||'';return type.includes('json')?res.json():res.blob() as T
}
export async function download(path:string,name:string){const blob=await api<Blob>(path);const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;a.click();URL.revokeObjectURL(url)}
