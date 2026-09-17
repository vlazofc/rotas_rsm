import {useEffect,useMemo,useRef,useState} from "react";
import api from "../services/api";
import {useAuth} from "../context/AuthContext";
import RouteMap from "../components/RouteMap";

type Live={route_id:number;codigo_ut:string;vehicle_plate?:string;driver_name?:string;latitude:number;longitude:number;speed_kmh?:number;recorded_at:string};
type DriverRoute={id:number;codigo_ut:string;status:string};
declare global {interface Window{AndroidLocation?:{requestPermission?:()=>void;requestAllPermissions?:()=>void;startLocationUpdates?:(intervalMs:number)=>void;stopLocationUpdates?:()=>void};onAndroidLocation?:(lat:number,lng:number,accuracy?:number,speedMps?:number,recordedAt?:string)=>void}}

export default function Tracking(){
 const {hasRole}=useAuth(),tower=hasRole('admin_global','gestor_brasil','torre_controle');
 const [live,setLive]=useState<Live[]>([]),[activeRoute,setActiveRoute]=useState<DriverRoute|null>(null),[selected,setSelected]=useState<number|null>(null),[fullscreen,setFullscreen]=useState(false),[checking,setChecking]=useState(true);
 const mapShell=useRef<HTMLDivElement|null>(null);
 async function refresh(){if(tower)setLive((await api.get('/tracking/live')).data);else{const {data}=await api.get<DriverRoute[]>('/routes');setActiveRoute(data.find(item=>item.status==='em_rota')??null);setChecking(false)}}
 useEffect(()=>{void refresh();const timer=window.setInterval(()=>void refresh(),30000);return()=>window.clearInterval(timer)},[tower]);
 useEffect(()=>{const change=()=>setFullscreen(document.fullscreenElement===mapShell.current);document.addEventListener('fullscreenchange',change);return()=>document.removeEventListener('fullscreenchange',change)},[]);
 async function toggleFullscreen(){if(!document.fullscreenElement)await mapShell.current?.requestFullscreen();else await document.exitFullscreen()}
 const mapRoutes=useMemo(()=>live.map(p=>({id:p.route_id,codigo_ut:p.codigo_ut,status:'em_rota',stops:[{id:p.route_id,customer_name:p.driver_name||'Motorista',vehicle_plate:p.vehicle_plate,latitude:p.latitude,longitude:p.longitude,status:'em_rota'}]})),[live]);
 if(!tower)return <div className="page-card tracking-page"><div className="page-header"><div><h2>Monitoramento GPS</h2><p className="page-subtitle">Ativo durante a rota, inclusive com o aplicativo em segundo plano.</p></div></div><div className="tracking-driver-status card-panel"><span className={`tracking-status-dot${activeRoute?' is-active':''}`}/><div><strong>{checking?'Verificando rota…':activeRoute?`Rota ${activeRoute.codigo_ut} em acompanhamento`:'Nenhuma rota em andamento'}</strong><small>{activeRoute?'O GPS é compartilhado automaticamente durante esta rota.':'O rastreamento será iniciado após a saída do CD e desligado quando todas as rotas forem finalizadas.'}</small></div></div></div>;
 return <div className="page-card tracking-page"><div className="page-header"><div><h2>Monitoramento GPS</h2><p className="page-subtitle">Acompanhamento da frota em tempo real dentro do ambiente operacional.</p></div><button className="btn-ghost tracking-fullscreen-btn" onClick={toggleFullscreen}>⛶ Tela cheia</button></div><div ref={mapShell} className={`tracking-map-shell${fullscreen?' is-fullscreen':''}`}><RouteMap routes={mapRoutes} selectedRouteId={selected} onSelectRoute={setSelected} variant="vehicle"/><div className="tracking-map-toolbar"><span>{live.length} veículo{live.length===1?'':'s'} monitorado{live.length===1?'':'s'}</span><button className="btn-primary btn-mini" onClick={toggleFullscreen}>{fullscreen?'✕ Sair da tela cheia':'⛶ Tela cheia'}</button></div></div><div className="card-grid">{live.map(p=><article className="summary-card" key={p.route_id}><h3>{p.codigo_ut} · {p.vehicle_plate||'-'}</h3><p>{p.driver_name||'-'} · {p.speed_kmh?.toFixed(1)||0} km/h</p><small>{new Date(p.recorded_at).toLocaleString('pt-BR')}</small></article>)}</div></div>
}
