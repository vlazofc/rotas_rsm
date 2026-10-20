import { useEffect, useState } from "react";
import api from "../services/api";

interface OriginBranch {
  id: number;
  name: string;
  default_origin_address: string | null;
  active: boolean;
}

interface Props {
  address: string;
  onSelect: (origin: { name: string; address: string }) => void;
  className?: string;
  disabled?: boolean;
}

const ORIGIN_NAMES = ["Salto", "Barueri"];

export default function RouteOriginSelect({ address, onSelect, className, disabled }: Props) {
  const [branches, setBranches] = useState<OriginBranch[]>([]);
  const [loadError, setLoadError] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get<OriginBranch[]>("/branches")
      .then(({ data }) => {
        setBranches(data.filter(branch => branch.active && ORIGIN_NAMES.includes(branch.name) && branch.default_origin_address)
          .sort((a, b) => ORIGIN_NAMES.indexOf(a.name) - ORIGIN_NAMES.indexOf(b.name)));
      })
      .catch(() => setLoadError(true))
      .finally(() => setLoading(false));
  }, []);

  const selected = branches.find(branch => branch.default_origin_address === address.trim());
  const value = selected ? String(selected.id) : address.trim() ? "existing" : "";

  return <>
    <select className={className} value={value} disabled={disabled || loading || loadError || branches.length === 0}
      aria-label="Origem do Marco 0" onChange={event => {
        const branch = branches.find(item => String(item.id) === event.target.value);
        if (branch?.default_origin_address) onSelect({ name: branch.name, address: branch.default_origin_address });
      }}>
      <option value="">Selecione Salto ou Barueri</option>
      {value === "existing" && <option value="existing">Origem já informada</option>}
      {branches.map(branch => <option key={branch.id} value={branch.id}>{branch.name}</option>)}
    </select>
    {loadError && <small>Não foi possível carregar as origens.</small>}
    {!loading && !loadError && branches.length === 0 && <small>Não há endereços de origem cadastrados para Salto ou Barueri.</small>}
  </>;
}
