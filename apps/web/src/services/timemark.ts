/** Grava data/hora e coordenadas na própria imagem antes do upload. */
export async function applyTimemark(file: File): Promise<File> {
  if (!file.type.startsWith("image/")) return file;
  const position = await new Promise<GeolocationPosition | null>((resolve) => {
    if (!navigator.geolocation) return resolve(null);
    navigator.geolocation.getCurrentPosition(resolve, () => resolve(null), { enableHighAccuracy: true, timeout: 6000 });
  });
  const bitmap = await createImageBitmap(file);
  const canvas = document.createElement("canvas"); canvas.width = bitmap.width; canvas.height = bitmap.height;
  const ctx = canvas.getContext("2d")!; ctx.drawImage(bitmap, 0, 0);
  const fontSize = Math.max(22, Math.round(canvas.width / 42)); const pad = Math.round(fontSize * .6);
  const location = position ? ` · ${position.coords.latitude.toFixed(6)}, ${position.coords.longitude.toFixed(6)}` : " · GPS indisponível";
  const label = `${new Date().toLocaleString("pt-BR")}${location}`;
  ctx.font = `600 ${fontSize}px sans-serif`; const width = ctx.measureText(label).width + pad * 2;
  ctx.fillStyle = "rgba(0,0,0,.68)"; ctx.fillRect(0, canvas.height-fontSize-pad*2, Math.min(width,canvas.width), fontSize+pad*2);
  ctx.fillStyle = "#fff"; ctx.fillText(label, pad, canvas.height-pad);
  const blob = await new Promise<Blob>((resolve,reject)=>canvas.toBlob(b=>b?resolve(b):reject(new Error("Falha ao processar imagem")),"image/jpeg",.88));
  return new File([blob], file.name.replace(/\.[^.]+$/, "")+"-timemark.jpg", { type:"image/jpeg", lastModified:Date.now() });
}
