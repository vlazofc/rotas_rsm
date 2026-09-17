export interface EvidenceContext { routeCode?:string|null; stopSequence?:number|null; address?:string|null; driverName?:string|null; vehiclePlate?:string|null; systemName?:string }
export type EvidenceStage="location"|"image"|"encoding";
const YELLOW="#f9a61a";
let logoPromise:Promise<HTMLImageElement|null>|undefined;

/** Cria um registro visual auditável na própria imagem antes do upload. */
export async function applyTimemark(file:File,meta:EvidenceContext={},onStage?:(stage:EvidenceStage)=>void):Promise<File>{
 if(!file.type.startsWith("image/"))return file;
 // Reduz fotos de alta resolução antes da marcação para não travar o WebView.
 onStage?.("location");
 const capturedAt=new Date();
 const [position,source,logo]=await Promise.all([locate(),createImageBitmap(file),loadLogo()]),maxSide=1600,ratio=Math.min(1,maxSide/Math.max(source.width,source.height)),canvas=document.createElement("canvas");canvas.width=Math.max(1,Math.round(source.width*ratio));canvas.height=Math.max(1,Math.round(source.height*ratio));
 onStage?.("image");
 const ctx=canvas.getContext("2d");if(!ctx){source.close();throw new Error("Não foi possível preparar a evidência.");}ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality="high";ctx.drawImage(source,0,0,canvas.width,canvas.height);source.close();
 const code=`ADMX-${Date.now().toString(36).toUpperCase()}-${crypto.randomUUID().replaceAll("-","").slice(0,10).toUpperCase()}`;
 const scale=Math.max(1,canvas.width/1080),side=Math.max(48*scale,canvas.width*.055),panel=Math.min(canvas.height*.52,Math.max(360*scale,canvas.height*.38)),pad=25*scale,maxW=canvas.width-side-pad*2;
 ctx.fillStyle="rgba(23,23,23,.92)";ctx.fillRect(canvas.width-side,0,side,canvas.height);ctx.fillStyle=YELLOW;ctx.fillRect(canvas.width-side,0,Math.max(5,6*scale),canvas.height);
 ctx.save();ctx.translate(canvas.width-side/2+3*scale,canvas.height-20*scale);ctx.rotate(-Math.PI/2);ctx.font=`700 ${Math.max(14,16*scale)}px sans-serif`;ctx.fillStyle="rgba(255,255,255,.9)";ctx.fillText(`${meta.systemName||"ADIMAX ROTAS"}  •  REGISTRO ${code}`,0,0);ctx.restore();
 const gradient=ctx.createLinearGradient(0,canvas.height-panel,0,canvas.height);gradient.addColorStop(0,"rgba(23,23,23,.2)");gradient.addColorStop(.18,"rgba(23,23,23,.84)");gradient.addColorStop(1,"rgba(23,23,23,.97)");ctx.fillStyle=gradient;ctx.fillRect(0,canvas.height-panel,canvas.width-side,panel);
 ctx.fillStyle=YELLOW;ctx.fillRect(pad,canvas.height-panel+30*scale,Math.max(5,6*scale),panel-60*scale);
 const lx=pad+22*scale,ly=canvas.height-panel+22*scale,lw=Math.min(220*scale,maxW*.3),lh=66*scale;ctx.fillStyle="rgba(255,255,255,.96)";ctx.beginPath();ctx.roundRect(lx,ly,lw,lh,9*scale);ctx.fill();
 if(logo){const ratio=Math.min((lw-22*scale)/logo.width,(lh-16*scale)/logo.height),w=logo.width*ratio,h=logo.height*ratio;ctx.drawImage(logo,lx+(lw-w)/2,ly+(lh-h)/2,w,h)}else{ctx.fillStyle="#171717";ctx.font=`900 ${25*scale}px sans-serif`;ctx.fillText("ADIMAX",lx+16*scale,ly+42*scale)}
 const date=new Intl.DateTimeFormat("pt-BR",{timeZone:"America/Sao_Paulo",weekday:"short",day:"2-digit",month:"short",year:"numeric",hour:"2-digit",minute:"2-digit",second:"2-digit"}).format(capturedAt).replaceAll(".","");
 const gps=position?`${position.coords.latitude.toFixed(6)}, ${position.coords.longitude.toFixed(6)}  •  precisão ±${Math.round(position.coords.accuracy)} m`:"Localização não autorizada ou indisponível";
 const route=[meta.routeCode&&`Rota ${meta.routeCode}`,meta.stopSequence&&`Parada ${meta.stopSequence}`].filter(Boolean).join("  •  "),driver=meta.driverName?.trim(),plate=meta.vehiclePlate?.trim(),lines=[date,route,driver&&`Motorista: ${driver}`,plate&&`Placa: ${plate.toUpperCase()}`,meta.address?.trim(),gps,`Código da evidência: ${code}`].filter(Boolean) as string[];
 let y=ly+lh+32*scale;ctx.fillStyle="#fff";ctx.textBaseline="alphabetic";for(const [i,line] of lines.entries()){const size=(i===0?24:19)*scale;ctx.font=`${i===0||i===lines.length-1?700:500} ${Math.max(15,size)}px sans-serif`;for(const part of wrap(ctx,line,maxW,2)){ctx.fillText(part,lx,y);y+=Math.max(23,size*1.3)}}
 ctx.globalAlpha=.12;ctx.fillStyle="#fff";ctx.font=`900 ${Math.max(30,44*scale)}px sans-serif`;ctx.textAlign="right";ctx.fillText(meta.systemName||"ADIMAX ROTAS",canvas.width-side-pad,canvas.height-18*scale);ctx.globalAlpha=1;
 onStage?.("encoding");
 const blob=await new Promise<Blob>((resolve,reject)=>canvas.toBlob(b=>b?resolve(b):reject(new Error("Falha ao processar imagem")),"image/jpeg",.78)),base=file.name.replace(/\.[^.]+$/,"").replace(/[^a-zA-Z0-9_-]+/g,"-").slice(0,55);
 return new File([blob],`${base}-${code}.jpg`,{type:"image/jpeg",lastModified:Date.now()});
}
function locate():Promise<GeolocationPosition|null>{return new Promise(resolve=>{
 if(!navigator.geolocation)return resolve(null);
 const timer=window.setTimeout(()=>resolve(null),1200);
 const finish=(position:GeolocationPosition|null)=>{window.clearTimeout(timer);resolve(position)};
 navigator.geolocation.getCurrentPosition(finish,()=>finish(null),{enableHighAccuracy:true,timeout:1000,maximumAge:120000});
})}
function loadLogo():Promise<HTMLImageElement|null>{
 return logoPromise??=new Promise(resolve=>{
  const img=new Image(),timer=window.setTimeout(()=>resolve(null),1000);
  img.onload=()=>{window.clearTimeout(timer);resolve(img)};
  img.onerror=()=>{window.clearTimeout(timer);resolve(null)};
  img.src="/brand/adimax-logo.png";
 });
}
function wrap(ctx:CanvasRenderingContext2D,text:string,width:number,max:number){const words=text.split(/\s+/),lines:string[]=[];let current="";for(const word of words){const next=current?`${current} ${word}`:word;if(ctx.measureText(next).width<=width||!current)current=next;else{lines.push(current);current=word;if(lines.length===max-1)break}}if(current&&lines.length<max)lines.push(current);return lines}
