import { FormEvent, useMemo, useState } from "react";
import RouteMap from "../components/RouteMap";
import api from "../services/api";

interface Result { origin_coords:{lat:number;lng:number}; destination_coords:{lat:number;lng:number}; waypoint_coords:{lat:number;lng:number}[]; ordered_destinations:string[]; geometry:number[][]; distance_km:number; duration_minutes:number|null }

export default function ManualRouting(){
  const [origin,setOrigin]=useState("");
  const [destinations,setDestinations]=useState<string[]>([""]);
  const [vehicle,setVehicle]=useState("car");
  const [optimize,setOptimize]=useState(true);
  const [result,setResult]=useState<Result|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const validCount=destinations.filter(x=>x.trim()).length;
  async function calculate(e:FormEvent){e.preventDefault();setBusy(true);setError("");try{const {data}=await api.post<Result>("/manual-routing",{origin:origin.trim(),destinations:destinations.map(x=>x.trim()).filter(Boolean),vehicle,optimize});setResult(data)}catch(err:any){setError(err?.response?.data?.detail??"Não foi possível calcular a rota.")}finally{setBusy(false)}}
  function update(index:number,value:string){setDestinations(items=>items.map((item,i)=>i===index?value:item))}
  function remove(index:number){setDestinations(items=>items.length===1?[""]:items.filter((_,i)=>i!==index))}
  function pasteList(){const text=window.prompt("Cole um endereço por linha:");if(!text)return;setDestinations(text.split(/\r?\n/).map(x=>x.trim()).filter(Boolean).slice(0,50))}
  const mapRoute=useMemo(()=>result?[{id:-1,codigo_ut:"ROTA MANUAL",status:"planejada",routing_geometry_json:JSON.stringify(result.geometry),stops:[...result.waypoint_coords,result.destination_coords].map((p,i)=>({id:i+1,sequence:i+1,customer_name:result.ordered_destinations[i]??`Destino ${i+1}`,status:"pendente",latitude:p.lat,longitude:p.lng}))}]:[],[result]);
  return <div className="manual-router-page">
    <div className="manual-router-map"><RouteMap routes={mapRoute} selectedRouteId={result?-1:null} onSelectRoute={()=>{}}/></div>
    <form className="manual-router-card" onSubmit={calculate}>
      <header><div><span>ROTEIRIZAÇÃO MANUAL</span><h1>Como você quer chegar?</h1><p>Pesquise uma origem e até 50 destinos.</p></div></header>
      <div className="manual-route-fields"><div className="manual-route-row"><i className="start"/><label><small>PONTO DE PARTIDA</small><input required value={origin} onChange={e=>setOrigin(e.target.value)} placeholder="Escolha o ponto de partida"/></label></div>{destinations.map((destination,index)=><div className="manual-route-row" key={index}><b>{index+1}</b><label><small>DESTINO {index+1}</small><input required value={destination} onChange={e=>update(index,e.target.value)} placeholder="Informe o endereço completo"/></label><button type="button" onClick={()=>remove(index)}>×</button></div>)}</div>
      <div className="manual-route-links"><button type="button" disabled={destinations.length>=50} onClick={()=>setDestinations(x=>[...x,""])}>+ Adicionar destino</button><button type="button" onClick={pasteList}>☷ Colar lista</button><small>{validCount}/50</small></div>
      <div className="manual-vehicles">{[["car","🚙 Carro"],["truck_medium","🚚 Caminhão"],["truck_articulated","🚛 Carreta"]].map(([id,label])=><button type="button" className={vehicle===id?"active":""} onClick={()=>setVehicle(id)} key={id}>{label}</button>)}</div>
      <label className="manual-optimize"><span>✦</span><div><strong>Otimizar ordem das paradas</strong><small>O Maestro reorganiza para reduzir o percurso</small></div><input type="checkbox" checked={optimize} onChange={e=>setOptimize(e.target.checked)}/></label>
      <button className="manual-calculate" disabled={busy||!origin.trim()||!validCount}>{busy?"Calculando a melhor rota…":"Calcular rota  →"}</button>
      {error&&<p className="manual-route-error">{error}</p>}{result&&<div className="manual-result"><strong>{result.distance_km} km</strong><span>{result.duration_minutes?`${Math.floor(result.duration_minutes/60)}h ${result.duration_minutes%60}min`:"—"}</span><small>{validCount} destino(s)</small></div>}
    </form>
    {busy&&<div className="manual-loading"><span/><strong>Calculando a melhor rota…</strong><small>Geocodificando e organizando as paradas</small></div>}
  </div>
}
