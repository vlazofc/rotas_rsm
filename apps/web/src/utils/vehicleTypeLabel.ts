export function vehicleTypeLabel(label: string | null | undefined): string {
  if (!label) return "—";
  const normalized = label.trim().normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .toLowerCase().replace(/^(?:caminhao|camiao)\s+/, "");
  const names: Record<string, string> = {
    furgao: "Van", van: "Van",
    "veiculo ligeiro de mercadorias": "Passeio", "veiculo leve de carga": "Passeio", passeio: "Passeio",
    vuc: "Vuc", toco: "Toco", truck: "Truck",
    frigorifico: "Refrigerado", refrigerado: "Refrigerado",
    "articulado (semi-reboque)": "Carreta", "articulado (carreta)": "Carreta", carreta: "Carreta",
    motociclo: "Moto", motocicleta: "Moto", moto: "Moto",
  };
  return names[normalized] || label.replace(/^(?:Caminhão|Camião)\s+/iu, "");
}
