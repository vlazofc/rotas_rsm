import {useEffect,useState} from "react";

type DialogRequest={kind:"confirm"|"prompt"|"alert";title:string;message:string;label?:string;initial?:string;required?:boolean;confirmLabel?:string;danger?:boolean;resolve:(value:boolean|string|null)=>void};
let listener:((request:DialogRequest)=>void)|null=null;
let pendingResolve:((value:boolean|string|null)=>void)|null=null;
const open=(request:Omit<DialogRequest,"resolve">)=>new Promise<boolean|string|null>(resolve=>{
 if(!listener){resolve(false);return}
 pendingResolve?.(false);
 pendingResolve=resolve;
 listener({...request,resolve:value=>{if(pendingResolve===resolve)pendingResolve=null;resolve(value)}});
});
export const appConfirm=(message:string,options:{title?:string;confirmLabel?:string;danger?:boolean}={})=>open({kind:"confirm",title:options.title||"Confirmar operação",message,confirmLabel:options.confirmLabel||"Confirmar",danger:options.danger}) as Promise<boolean>;
export const appPrompt=(message:string,options:{title?:string;label?:string;initial?:string;required?:boolean;confirmLabel?:string}={})=>open({kind:"prompt",title:options.title||"Informações necessárias",message,label:options.label,initial:options.initial||"",required:options.required,confirmLabel:options.confirmLabel||"Continuar"}) as Promise<string|null>;
export const appAlert=(message:string,options:{title?:string}={})=>open({kind:"alert",title:options.title||"Atenção",message,confirmLabel:"Entendi"}) as Promise<boolean>;

export default function AppDialogHost(){
 const [dialog,setDialog]=useState<DialogRequest|null>(null),[value,setValue]=useState("");
 useEffect(()=>{listener=request=>{setValue(request.initial||"");setDialog(request)};return()=>{listener=null}},[]);
 function finish(result:boolean|string|null){dialog?.resolve(result);setDialog(null)}
 if(!dialog)return null;
 const valid=dialog.kind!=="prompt"||!dialog.required||value.trim().length>0;
 return <div className="modal-backdrop app-dialog-backdrop" onClick={()=>dialog.kind==="alert"?finish(true):finish(dialog.kind==="confirm"?false:null)}><section className="modal-card app-dialog" role="alertdialog" aria-modal="true" aria-labelledby="app-dialog-title" onClick={event=>event.stopPropagation()}><div className={`app-dialog-icon ${dialog.danger?"is-danger":""}`}>{dialog.danger?"!":dialog.kind==="prompt"?"✎":"✓"}</div><div className="app-dialog-copy"><span className="app-dialog-eyebrow">ADIMAX</span><h3 id="app-dialog-title">{dialog.title}</h3><p>{dialog.message}</p></div>{dialog.kind==="prompt"&&<label className="field app-dialog-field"><span>{dialog.label||"Descrição"}</span><textarea className="input" autoFocus rows={4} required={dialog.required} value={value} onChange={event=>setValue(event.target.value)} onKeyDown={event=>{if(event.key==="Enter"&&(event.ctrlKey||event.metaKey)&&valid)finish(value.trim())}}/><small>Use Ctrl + Enter para confirmar.</small></label>}<div className="modal-actions"><button autoFocus={dialog.kind!=="prompt"} className={dialog.danger?"btn-danger":"btn-primary"} type="button" disabled={!valid} onClick={()=>finish(dialog.kind==="prompt"?value.trim():true)}>{dialog.confirmLabel}</button>{dialog.kind!=="alert"&&<button className="btn-ghost" type="button" onClick={()=>finish(dialog.kind==="confirm"?false:null)}>Cancelar</button>}</div></section></div>
}
