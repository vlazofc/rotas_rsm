import api from "./api";
import { appConfirm } from "../components/AppDialog";

const fields: Record<string,string> = {
  route_date:"Data da rota", delivery_date:"Data de entrega", spreadsheet_route:"Rota da planilha",
  driver_id:"Motorista (ID)", vehicle_id:"Veículo (ID)", origin_address:"Origem (CD)",
  customer_name:"Cliente", customer_address:"Endereço", city:"Cidade", sequence:"Sequência",
  spreadsheet_sequence:"Sequência da planilha", invoice_number:"Nota fiscal", cte_number:"CT-e",
  weight_kg:"Peso", administrative_notes:"Observação", customer_notes:"Observação do cliente",
  customer_notes_2:"Observação do cliente 2", daily_count:"Diárias", overnight:"Pernoite",
  vehicle_profile_sent:"Perfil enviado", vehicle_profile_requested:"Perfil solicitado",
};

export async function importRoutes<T>(body: FormData): Promise<T | null> {
  try {
    return (await api.post<T>("/routes-import/upload", body)).data;
  } catch (error: any) {
    const detail = error?.response?.data?.detail;
    if (error?.response?.status !== 409 || detail?.code !== "import_confirmation_required") throw error;
    const changes = detail.changes.map((change: any, index: number) =>
      `${index + 1}. Rota ${change.route} — ${fields[change.field] || change.field}: “${change.old ?? "vazio"}” → “${change.new ?? "vazio"}”`
    ).join("\n");
    const approved = await appConfirm(
      `${detail.total} alteração(ões) em registros existentes. Primeiras ${detail.changes.length}:\n\n${changes}\n\nAutorizar todas as alterações desta planilha? Sua autorização e os valores anteriores e novos serão registrados.`,
      {title:"Confirmar sobreposição da planilha", confirmLabel:"Autorizar e importar", danger:true},
    );
    if (!approved) return null;
    body.set("confirm_overwrite", "true");
    return (await api.post<T>("/routes-import/upload", body)).data;
  }
}
