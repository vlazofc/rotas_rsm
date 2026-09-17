import { FormEvent, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import api from "../services/api";
import { useAuth } from "../context/AuthContext";
import "./Gallery.css";

interface GalleryItem { id:string; kind:string; occurred_at:string; vehicle_plate?:string|null; driver_name?:string|null; reference?:string|null; filename:string; content_type?:string|null; url:string; attachment_id:number; evidence_code?:string|null }
interface Driver { id:number; name:string; active:boolean }
interface Vehicle { id:number; plate:string; active:boolean }
type Filters = { query:string; plate:string; driver_id:string; kind:string; start:string; end:string };

const KINDS = ["entrega", "devolucao", "manutencao", "orcamento"];
const EMPTY_FILTERS: Filters = { query:"", plate:"", driver_id:"", kind:"", start:"", end:"" };
const isImage = (contentType?:string|null) => !!contentType?.startsWith("image/");
const formatDate = (value:string) => new Date(`${value}T12:00:00`).toLocaleDateString("pt-BR");

function ProtectedThumbnail({item}:{item:GalleryItem}) {
  const [source,setSource] = useState("");
  useEffect(() => {
    let objectUrl="",active=true;
    api.get(`/gallery/files/${item.attachment_id}`,{responseType:"blob"}).then(({data})=>{if(active){objectUrl=URL.createObjectURL(data);setSource(objectUrl);}}).catch(()=>setSource(""));
    return ()=>{active=false;if(objectUrl)URL.revokeObjectURL(objectUrl);};
  },[item.attachment_id]);
  return source?<img src={source} alt={item.filename} loading="lazy"/>:<div className="gallery-image-loading">Imagem</div>;
}

export default function Gallery() {
  const { t } = useTranslation();
  const { hasRole } = useAuth();
  const [items,setItems] = useState<GalleryItem[]>([]);
  const [drivers,setDrivers] = useState<Driver[]>([]);
  const [vehicles,setVehicles] = useState<Vehicle[]>([]);
  const [filters,setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [applied,setApplied] = useState<Filters>(EMPTY_FILTERS);
  const [loading,setLoading] = useState(false);
  const [error,setError] = useState("");

  useEffect(() => {
    Promise.all([api.get<Driver[]>("/drivers"),api.get<Vehicle[]>("/vehicles")])
      .then(([driverResponse,vehicleResponse]) => { setDrivers(driverResponse.data); setVehicles(vehicleResponse.data); })
      .catch(() => { setDrivers([]); setVehicles([]); });
    void search(EMPTY_FILTERS);
  }, []);

  async function search(nextFilters = filters) {
    if (nextFilters.start && nextFilters.end && nextFilters.start > nextFilters.end) { setError("A data inicial não pode ser posterior à data final."); return; }
    setLoading(true); setError("");
    try {
      const {data} = await api.get<GalleryItem[]>("/gallery", {params:{
        query:nextFilters.query.trim() || undefined, plate:nextFilters.plate || undefined,
        driver_id:nextFilters.driver_id ? Number(nextFilters.driver_id) : undefined,
        kind:nextFilters.kind || undefined, start:nextFilters.start || undefined, end:nextFilters.end || undefined,
      }});
      setItems(data); setApplied(nextFilters);
    } catch (requestError:any) { setItems([]); setError(requestError?.response?.data?.detail || "Não foi possível consultar os documentos."); }
    finally { setLoading(false); }
  }

  function submit(event:FormEvent) { event.preventDefault(); void search(); }
  function clearFilters() { setFilters(EMPTY_FILTERS); void search(EMPTY_FILTERS); }
  async function openFile(item:GalleryItem) {
    setError("");
    const documentWindow=window.open("","_blank");
    try {
      const {data}=await api.get(`/gallery/files/${item.attachment_id}`,{responseType:"blob"});
      const objectUrl=URL.createObjectURL(data);if(documentWindow)documentWindow.location.href=objectUrl;else window.location.href=objectUrl;
      window.setTimeout(()=>URL.revokeObjectURL(objectUrl),60000);
    } catch(requestError:any) { documentWindow?.close();setError(requestError?.response?.data?.detail||"Não foi possível abrir este documento."); }
  }
  async function remove(item:GalleryItem,requestNew=false) {
    if(!window.confirm(requestNew?"Remover a foto atual e solicitar uma nova ao motorista?":"Excluir definitivamente esta foto?"))return;
    setError("");
    try {
      if(requestNew)await api.post(`/gallery/${item.attachment_id}/request-new`);
      else await api.delete(`/gallery/${item.attachment_id}`);
      await search(applied);
    } catch(requestError:any) { setError(requestError?.response?.data?.detail||"Não foi possível concluir a ação."); }
  }
  const activeCount = Object.values(applied).filter(Boolean).length;

  return <div className="gallery-page">
    <div className="page-header"><div><h2>{t("gallery.title")}</h2><p className="page-subtitle">Comprovantes, fotos e documentos organizados em um só lugar.</p></div><div className="gallery-result-count"><strong>{items.length}</strong><span>documento{items.length===1?"":"s"}</span></div></div>
    <form className="card-panel gallery-filters" onSubmit={submit}>
      <label className="field gallery-query"><span>Buscar documento ou registro</span><input className="input" placeholder="Código ADMX, nome, rota ou motorista" value={filters.query} onChange={event=>setFilters({...filters,query:event.target.value})}/></label>
      <label className="field"><span>Placa</span><select className="input" value={filters.plate} onChange={event=>setFilters({...filters,plate:event.target.value})}><option value="">Todas as placas</option>{vehicles.filter(vehicle=>vehicle.active).sort((a,b)=>a.plate.localeCompare(b.plate)).map(vehicle=><option key={vehicle.id} value={vehicle.plate}>{vehicle.plate}</option>)}</select></label>
      <label className="field"><span>Motorista</span><select className="input" value={filters.driver_id} onChange={event=>setFilters({...filters,driver_id:event.target.value})}><option value="">Todos os motoristas</option>{drivers.filter(driver=>driver.active).sort((a,b)=>a.name.localeCompare(b.name)).map(driver=><option key={driver.id} value={driver.id}>{driver.name}</option>)}</select></label>
      <label className="field"><span>Tipo</span><select className="input" value={filters.kind} onChange={event=>setFilters({...filters,kind:event.target.value})}><option value="">Todos os tipos</option>{KINDS.map(kind=><option key={kind} value={kind}>{t(`gallery.kinds.${kind}`)}</option>)}</select></label>
      <label className="field"><span>Data inicial</span><input className="input" type="date" value={filters.start} onChange={event=>setFilters({...filters,start:event.target.value})}/></label>
      <label className="field"><span>Data final</span><input className="input" type="date" min={filters.start||undefined} value={filters.end} onChange={event=>setFilters({...filters,end:event.target.value})}/></label>
      <div className="gallery-filter-actions"><button type="button" className="btn-ghost" disabled={loading||(!activeCount&&!Object.values(filters).some(Boolean))} onClick={clearFilters}>Limpar</button><button className="btn-primary" disabled={loading}>{loading?"Buscando…":"Buscar"}</button></div>
      {activeCount>0&&<div className="gallery-applied">{activeCount} filtro{activeCount===1?"":"s"} aplicado{activeCount===1?"":"s"}</div>}
      {error&&<p className="modal-error gallery-filter-error">{error}</p>}
    </form>
    {loading?<div className="gallery-loading">Consultando documentos…</div>:<div className="gallery-grid">
      {items.map(item=><article key={item.id} className="gallery-card"><button type="button" onClick={()=>void openFile(item)} className="gallery-card-open"><div className="gallery-thumb">{isImage(item.content_type)?<ProtectedThumbnail item={item}/>:<div className="gallery-file-icon"><span>PDF</span></div>}<span className="gallery-kind">{t(`gallery.kinds.${item.kind}`)}</span></div><div className="gallery-card-body"><strong title={item.filename}>{item.filename}</strong>{item.evidence_code&&<code className="gallery-evidence-code">{item.evidence_code}</code>}<div className="gallery-meta"><span>📅 {formatDate(item.occurred_at)}</span>{item.vehicle_plate&&<span>🚚 {item.vehicle_plate}</span>}{item.driver_name&&<span>● {item.driver_name}</span>}</div>{item.reference&&<p>{item.reference}</p>}<span className="gallery-open">Abrir documento ↗</span></div></button>{hasRole("admin_global")&&item.kind==="entrega"&&<footer className="gallery-admin-actions"><button type="button" onClick={()=>void remove(item,true)}>Solicitar nova</button><button type="button" className="danger" onClick={()=>void remove(item)}>Excluir</button></footer>}</article>)}
      {!items.length&&<div className="empty-state gallery-empty"><strong>Nenhum documento encontrado</strong><span>Revise os filtros ou clique em “Limpar” para consultar toda a galeria.</span></div>}
    </div>}
  </div>;
}
