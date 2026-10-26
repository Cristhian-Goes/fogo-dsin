"""Cérebro do F.O.G.O.

A Parte 1 vive no cadastro (equipamentos, agentes e validação).
A Parte 2 vive nos indicadores, alertas e na fotografia que a central consome.
A Parte 3 vive no Índice de Pressão Operacional: uma conta explicável,
não uma caixa-preta. O histórico é sintético e reprodutível (semente 20261020),
com um perfil urbano explícito de Marília, Assis e Cândido Mota.
"""

from __future__ import annotations

import math
import random
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any

try:
    from zoneinfo import ZoneInfo

    TZ = ZoneInfo("America/Sao_Paulo")
except Exception:  # pragma: no cover
    TZ = timezone(timedelta(hours=-3))

SEED = 20261020
SCHEMA = 3
HISTORY_DAYS = 90
ANOMALY_WINDOW_H = 3
CAPACITY = 0.85
REF_IPO = 2.35
BASE = 0.42

REGIONS: dict[str, dict[str, Any]] = {
    "Centro Marília": {
        "lat": -22.2142, "lng": -49.9458, "city": "Marília", "uf": "SP",
        "cep_prefix": "17500", "radius": 900,
    },
    "Campus": {
        "lat": -22.2298, "lng": -49.9332, "city": "Marília", "uf": "SP",
        "cep_prefix": "17525", "radius": 800,
    },
    "Sampaio Vidal": {
        "lat": -22.2176, "lng": -49.9634, "city": "Marília", "uf": "SP",
        "cep_prefix": "17509", "radius": 1100,
    },
    "Alto Cafezal": {
        "lat": -22.2412, "lng": -49.9575, "city": "Marília", "uf": "SP",
        "cep_prefix": "17515", "radius": 1000,
    },
    "Fragata": {
        "lat": -22.2055, "lng": -49.9788, "city": "Marília", "uf": "SP",
        "cep_prefix": "17519", "radius": 1100,
    },
    "Centro Assis": {
        "lat": -22.6617, "lng": -50.4120, "city": "Assis", "uf": "SP",
        "cep_prefix": "19800", "radius": 1200,
    },
    "Vila Xavier": {
        "lat": -22.6488, "lng": -50.3975, "city": "Assis", "uf": "SP",
        "cep_prefix": "19806", "radius": 1000,
    },
    "Cândido Mota": {
        "lat": -22.7461, "lng": -50.3872, "city": "Cândido Mota", "uf": "SP",
        "cep_prefix": "19880", "radius": 1400,
    },
}

# Curva de uma cidade: madrugada baixa, dois picos de deslocamento, noite em queda.
HOUR_SHAPE = [
    0.22, 0.16, 0.14, 0.13, 0.14, 0.30,
    0.62, 1.40, 1.60, 1.20,
    0.92, 0.88,
    1.05, 0.98,
    0.95, 1.05, 1.20,
    1.50, 1.75, 1.30,
    0.90, 0.70,
    0.48, 0.32,
]

# base: peso da região. rush/night: dia útil. weekend*: sábado e domingo.
PROFILES = {
    "Centro Marília": dict(base=1.15, rush=1.25, night=1.15, weekend=0.85, weekend_night=1.15, academic=1.0),
    "Campus": dict(base=0.82, rush=1.30, night=0.45, weekend=0.40, weekend_night=0.45, academic=1.22),
    "Centro Assis": dict(base=0.78, rush=0.80, night=1.20, weekend=1.75, weekend_night=2.70, academic=1.0),
    "Vila Xavier": dict(base=0.72, rush=0.75, night=0.95, weekend=2.05, weekend_night=2.35, academic=1.0),
    "Alto Cafezal": dict(base=0.62, rush=0.85, night=0.70, weekend=1.90, weekend_night=1.40, academic=1.0),
    "Sampaio Vidal": dict(base=1.28, rush=1.58, night=0.55, weekend=0.58, weekend_night=0.70, academic=1.0),
    "Fragata": dict(base=1.08, rush=1.42, night=0.50, weekend=0.75, weekend_night=0.72, academic=1.0),
    "Cândido Mota": dict(base=0.84, rush=1.30, night=0.48, weekend=0.70, weekend_night=0.62, academic=1.0),
}

STREETS = {
    "Centro Marília": ["Rua São Luiz", "Rua Bahia", "Avenida Rio Branco", "Rua 9 de Julho"],
    "Campus": ["Avenida Hygino Muzy Filho", "Rua José Bonifácio", "Rua Carmo Silva"],
    "Centro Assis": ["Avenida Rui Barbosa", "Rua Minas Gerais", "Avenida Getúlio Vargas"],
    "Vila Xavier": ["Rua Paraná", "Avenida Otto Barreto", "Rua São Paulo"],
    "Alto Cafezal": ["Avenida das Indústrias", "Rua Bahia", "Avenida Castro Alves"],
    "Sampaio Vidal": ["Avenida Sampaio Vidal", "Avenida das Esmeraldas", "Rua Santa Helena"],
    "Fragata": ["Avenida República", "Rua Minas Gerais", "Avenida das Esmeraldas"],
    "Cândido Mota": ["SP-333", "Avenida Brasil", "Rua São Paulo"],
}

NEIGHBORHOODS = {
    "Centro Marília": ["Centro", "Higienópolis"],
    "Campus": ["Campus Universitário", "Jardim Universitário"],
    "Centro Assis": ["Centro", "Vila Rodrigues"],
    "Vila Xavier": ["Vila Xavier", "Jardim Paraná"],
    "Alto Cafezal": ["Alto Cafezal", "Jardim Maria Izabel"],
    "Sampaio Vidal": ["Sampaio Vidal", "Jardim Esmeralda"],
    "Fragata": ["Fragata", "Parque das Esmeraldas"],
    "Cândido Mota": ["Centro", "Jardim Santa Cruz"],
}

TEAMS = {
    "Centro Marília": "Equipe Centro",
    "Campus": "Equipe Campus",
    "Centro Assis": "Equipe Assis",
    "Vila Xavier": "Equipe Xavier",
    "Alto Cafezal": "Equipe Cafezal",
    "Sampaio Vidal": "Equipe Sampaio",
    "Fragata": "Equipe Fragata",
    "Cândido Mota": "Equipe Mota",
}

SENSOR_TYPES = {"radar", "camera", "balanca", "cancela", "totem"}
MOVING_TYPES = {"veiculo_autonomo", "transporte", "moto_agente", "viatura_gm", "viatura_pm"}
BAD_STATUS = {"mau_funcionamento", "em_manutencao", "desativado", "furtado"}
UNAVAILABLE = BAD_STATUS
ACTIVE_AGENT = {"em_atividade", "em_deslocamento"}

EQUIPMENT_STATUSES = [
    ("ainda_nao_instalado", "Ainda não instalado"),
    ("operacional", "Operacional"),
    ("mau_funcionamento", "Mau funcionamento"),
    ("em_manutencao", "Em manutenção"),
    ("desativado", "Desativado"),
    ("furtado", "Furtado"),
]
AGENT_STATUSES = [
    ("em_atividade", "Em atividade"),
    ("em_deslocamento", "Em deslocamento"),
    ("em_pausa", "Em pausa"),
    ("fora_de_servico", "Fora de serviço"),
]
MAINTENANCE_NEEDS = [
    ("nenhuma", "Nenhuma"),
    ("imediata", "Imediata"),
    ("agendada", "Agendada"),
]
SHIFTS = ["Manhã", "Tarde", "Noite"]
LEVELS = [
    (75, "critica", "crítica"),
    (50, "pressao", "pressão"),
    (30, "atencao", "atenção"),
    (0, "estavel", "estável"),
]

METHOD = {
    "name": "Índice de Pressão Operacional",
    "version": "1.0",
    "summary": (
        "O IPO estima, de 0 a 100, a pressão de ocorrências de uma região em uma hora. "
        "Ele nasce da média histórica daquele bairro, no mesmo dia da semana e na mesma hora, "
        "com um peso igual para as quatro ocorrências mais recentes desse recorte. "
        "Sensores indisponíveis aumentam o índice. A escala de agentes não entra no índice: "
        "ela aparece ao lado, como déficit, para a decisão não misturar 'a rua está carregada' "
        "com 'faltou gente'."
    ),
    "formula": "IPO = mínimo entre 100 e 100 × (média combinada × fator de sensores) ÷ 2,35",
    "inputs": [
        "90 dias de ocorrências sintéticas por região, dia da semana e hora",
        "Situação atual dos sensores (radar, câmera, balança, cancela e totem)",
        "Escala dos agentes por turno e região, e quem está de fato em campo agora",
        "Ocorrências analíticas das últimas 3 horas, para anomalia",
        "Série de uso de radares, patinetes e câmeras, e a disponibilidade do cadastro",
    ],
    "assumptions": [
        "O histórico é sintético e reprodutível. Dia útil concentra a Sampaio Vidal e o comércio de Marília; fim de semana concentra Assis. A variação em torno do perfil é curta. A Sampaio Vidal sobe devagar ao longo dos 90 dias.",
        "A referência 2,35 ocorrências por hora na região é pressão extrema e leva o IPO a 100.",
        "Cada agente da escala absorve cerca de 0,85 ocorrência por hora na sua região. Acima disso, a conta pede reforço.",
        "O que está quebrado, furtado ou desativado agora continua assim no dia projetado, até alguém mudar o cadastro.",
        "Anomalia não é previsão: é o presente fora da própria média. A janela é de 3 horas.",
        "Ciência numa ocorrência tira o evento do mapa. Não conserta a causa.",
    ],
}


def now_local() -> datetime:
    return datetime.now(TZ)


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def fmt_num(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def level_of(ipo: int) -> tuple[str, str]:
    for threshold, key, label in LEVELS:
        if ipo >= threshold:
            return key, label
    return "estavel", "estável"


def shift_of(hour: int) -> str:
    if 6 <= hour < 14:
        return "Manhã"
    if 14 <= hour < 22:
        return "Tarde"
    return "Noite"


def lambda_of(region: str, dow: int, hour: int, day_index: int = 0) -> float:
    profile = PROFILES[region]
    lam = BASE * profile["base"] * HOUR_SHAPE[hour]
    weekend = dow >= 5
    if weekend:
        if hour >= 17 or hour <= 1:
            lam *= profile["weekend_night"]
        else:
            lam *= profile["weekend"]
    else:
        if hour in (7, 8, 9, 17, 18, 19):
            lam *= profile["rush"]
        elif hour <= 5 or hour >= 22:
            lam *= profile["night"]
        if region == "Campus" and 8 <= hour <= 17:
            lam *= profile["academic"]
    if region == "Sampaio Vidal":
        lam *= 1 + 0.005 * day_index
    return lam


def noisy_count(rng: random.Random, lam: float) -> int:
    """Contagem estável em torno do perfil.

    A variação existe, mas é curta de propósito: a demonstração precisa
    contar a mesma história da ponte e da orla em qualquer horário de correção.
    """
    if lam <= 0:
        return 0
    jitter = (rng.random() - 0.5) * 0.45
    return max(0, int(round(lam + jitter)))


def _select(key: str, label: str, options: list[str], optional: bool = False) -> dict[str, Any]:
    return {"key": key, "label": label, "type": "select", "options": options, "optional": optional}


def _number(key: str, label: str, min_v: float, max_v: float, optional: bool = False, show_if: dict | None = None) -> dict[str, Any]:
    field = {"key": key, "label": label, "type": "number", "min": min_v, "max": max_v, "optional": optional}
    if show_if:
        field["show_if"] = show_if
    return field


def _text(key: str, label: str, optional: bool = False) -> dict[str, Any]:
    return {"key": key, "label": label, "type": "text", "optional": optional, "max": 60}


def _bool(key: str, label: str) -> dict[str, Any]:
    return {"key": key, "label": label, "type": "bool", "optional": False}


TYPES: dict[str, dict[str, Any]] = {
    "radar": {
        "label": "Radar de fiscalização", "role": "sensor", "moves": False,
        "fields": [
            _select("radar_kind", "Tipo de fiscalização", ["Velocidade", "Semáforo", "Retorno proibido", "Conversão proibida", "Faixa exclusiva"]),
            _number("speed_limit", "Velocidade máxima (km/h)", 20, 130, optional=True, show_if={"radar_kind": "Velocidade"}),
            _number("lanes", "Faixas monitoradas", 1, 8),
        ],
    },
    "camera": {
        "label": "Câmera de videomonitoramento", "role": "sensor", "moves": False,
        "fields": [
            _bool("night_vision", "Visão noturna"),
            _select("resolution", "Resolução", ["720p", "1080p", "4K"]),
            _select("image_mode", "Imagem", ["Colorida", "Preto e branco"]),
            _bool("ptz", "PTZ (movimento remoto)"),
        ],
    },
    "balanca": {
        "label": "Balança de caminhão", "role": "sensor", "moves": False,
        "fields": [
            _number("capacity_tons", "Capacidade (toneladas)", 10, 80),
            _number("axles", "Eixos aferidos", 2, 9),
        ],
    },
    "veiculo_autonomo": {
        "label": "Veículo autônomo de estacionamento", "role": "frota", "moves": True,
        "fields": [
            _text("plate", "Placa"),
            _number("range_km", "Autonomia (km)", 20, 200),
            _number("autonomy_hours", "Autonomia (horas)", 2, 16),
        ],
    },
    "cancela": {
        "label": "Cancela automatizada", "role": "sensor", "moves": False,
        "fields": [
            _select("direction", "Sentido", ["Entrada", "Saída", "Ambos"]),
            _text("linked_place", "Pátio ou área vinculada"),
        ],
    },
    "transporte": {
        "label": "Veículo de transporte", "role": "frota", "moves": True,
        "fields": [
            _select("category", "Categoria", ["Táxi", "Mototáxi", "Escolar"]),
            _text("plate", "Placa"),
            _text("license", "Licença ou alvará"),
            _number("seats", "Lugares", 1, 60),
            _bool("in_service", "Em serviço agora"),
        ],
    },
    "totem": {
        "label": "Totem de autoatendimento", "role": "sensor", "moves": False,
        "fields": [
            _select("payments", "Pagamentos", ["Pix e cartão", "Pix, cartão e dinheiro", "Somente Pix"]),
            _number("spots", "Vagas geridas", 10, 400),
        ],
    },
    "patinete": {
        "label": "Patinetes elétricos (ponto)", "role": "frota", "moves": False,
        "fields": [
            _number("fleet_size", "Patinetes no ponto", 4, 40),
            _number("avg_battery", "Carga média (%)", 0, 100),
            _text("operator", "Operador"),
        ],
    },
    "moto_agente": {
        "label": "Moto de agente de trânsito", "role": "frota", "moves": True,
        "fields": [_text("plate", "Placa"), _text("prefix", "Prefixo")],
    },
    "viatura_gm": {
        "label": "Viatura da Guarda Municipal", "role": "frota", "moves": True,
        "fields": [_text("plate", "Placa"), _text("prefix", "Prefixo"), _text("unit", "Unidade")],
    },
    "viatura_pm": {
        "label": "Viatura da Polícia Militar", "role": "frota", "moves": True,
        "fields": [_text("plate", "Placa"), _text("prefix", "Prefixo"), _text("unit", "Unidade")],
    },
}

BRANDS = {
    "radar": [("Velsis", "Velox R-310"), ("Perkons", "Pardal Compact"), ("Pumatronix", "ITSCAM VTR")],
    "camera": [("Intelbras", "VIP 3240"), ("Hikvision", "DS-2CD"), ("Axis", "P3265")],
    "balanca": [("Toledo", "Guardião 950"), ("Líder", "Balança BR-80")],
    "veiculo_autonomo": [("Urbanix", "Sentinela S2")],
    "cancela": [("Peccinin", "Cancela Gatter"), ("Intelbras", "CA 4500")],
    "transporte": [("Fiat", "Cronos"), ("Honda", "CG 160"), ("Renault", "Master")],
    "totem": [("Urbanix", "Totem Orla")],
    "patinete": [("Giro", "Hub Giro")],
    "moto_agente": [("Honda", "CB 500")],
    "viatura_gm": [("Toyota", "Hilux"), ("Chevrolet", "S10")],
    "viatura_pm": [("Chevrolet", "Trailblazer"), ("Toyota", "SW4")],
}

PREFIX = {
    "radar": "RAD", "camera": "CAM", "balanca": "BAL", "veiculo_autonomo": "VAF",
    "cancela": "CAN", "transporte": "TRP", "totem": "TOT", "patinete": "PAT",
    "moto_agente": "MOT", "viatura_gm": "VGM", "viatura_pm": "VPM",
}

AGENCIES = [
    "Secretaria de Mobilidade",
    "Guarda Municipal",
    "Polícia Militar",
    "DETRAN/SP",
    "Operador de micromobilidade",
    "Permissionário de transporte",
]

PEOPLE = [
    "Ana Luiza Ferreira", "Bruno Henrique Alves", "Camila dos Santos", "Diego Martins Rocha",
    "Elena Carvalho", "Felipe Andrade", "Gabriela Nunes", "Heitor Lima",
    "Irene Batista", "João Pedro Molina", "Larissa Teixeira", "Marcos Vinícius Dias",
    "Natália Prado", "Otávio Remor", "Paula Cristina Melo", "Rafael Antunes",
    "Sandra Regina Lopes", "Tiago Bastos", "Úrsula Klein", "Vitor Hugo Peixoto",
    "Wanda Cristina Ruiz", "Yasmin Duarte", "Caio Henrique Vogel", "Marina Costa",
]


def schema_public() -> dict[str, Any]:
    types = []
    for key, spec in TYPES.items():
        types.append({
            "id": key,
            "label": spec["label"],
            "role": spec["role"],
            "moves": spec["moves"],
            "fields": spec["fields"],
        })
    return {
        "types": types,
        "statuses": [{"id": k, "label": v} for k, v in EQUIPMENT_STATUSES],
        "agent_statuses": [{"id": k, "label": v} for k, v in AGENT_STATUSES],
        "maintenance": [{"id": k, "label": v} for k, v in MAINTENANCE_NEEDS],
        "shifts": SHIFTS,
        "agencies": AGENCIES,
        "regions": [
            {"id": name, "city": meta["city"], "uf": meta["uf"], "lat": meta["lat"], "lng": meta["lng"]}
            for name, meta in REGIONS.items()
        ],
    }


def _bucket_key(region: str, dow: int, hour: int) -> str:
    return f"{region}|{dow}|{hour}"


def summarize_counts(counts: list[int]) -> tuple[float, float, int, float, float]:
    if not counts:
        return 0.0, 0.35, 0, 0.0, 0.0
    mean = sum(counts) / len(counts)
    if len(counts) >= 2:
        var = sum((c - mean) ** 2 for c in counts) / len(counts)
        std = math.sqrt(var)
    else:
        std = 0.35
    recent_slice = counts[-4:]
    recent = sum(recent_slice) / len(recent_slice)
    blended = 0.5 * mean + 0.5 * recent
    return mean, std, len(counts), recent, blended


def bucket_stats(data: dict, region: str, dow: int, hour: int) -> tuple[float, float, int, float, float]:
    raw = data["history"]["buckets"].get(_bucket_key(region, dow, hour), [])
    return summarize_counts(raw)


def maintenance_flag(eq: dict, today: date) -> str | None:
    if eq.get("maintenance_need") == "imediata" or eq.get("status") == "mau_funcionamento":
        return "imediata"
    nxt = eq.get("next_maintenance")
    if nxt and eq.get("maintenance_need") == "agendada":
        due = date.fromisoformat(nxt)
        if due < today:
            return "atrasada"
        if (due - today).days <= 7:
            return "proxima"
    return None


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def _jitter(rng: random.Random, lat: float, lng: float, meters: float = 550) -> tuple[float, float]:
    dlat = (rng.random() - 0.5) * 2 * meters / 111_320
    dlng = (rng.random() - 0.5) * 2 * meters / (111_320 * math.cos(math.radians(lat)))
    return round(lat + dlat, 6), round(lng + dlng, 6)


def _reference(rng: random.Random, street: str) -> str:
    if street.startswith("BR-") or street.startswith("Rodovia"):
        return f"KM {rng.randint(180, 220)}"
    kind = rng.choices(["n", "o", "s", "m"], weights=[5, 3, 2, 1])[0]
    if kind == "n":
        return f"número {rng.randint(20, 980)}"
    if kind == "o":
        return f"oposto ao número {rng.randint(20, 980)}"
    if kind == "s":
        return "S/N"
    return "em frente ao Mercado do Tio"


def _cep(rng: random.Random, prefix: str) -> str:
    return f"{prefix}-{rng.randint(0, 999):03d}"


def _default_attrs(typ: str, index: int) -> dict[str, Any]:
    if typ == "radar":
        kinds = ["Velocidade", "Semáforo", "Retorno proibido", "Conversão proibida", "Faixa exclusiva", "Velocidade"]
        kind = kinds[index % len(kinds)]
        attrs: dict[str, Any] = {"radar_kind": kind, "lanes": (index % 3) + 1}
        if kind == "Velocidade":
            attrs["speed_limit"] = [40, 50, 60, 70][index % 4]
        return attrs
    if typ == "camera":
        return {
            "night_vision": index % 3 != 0,
            "resolution": ["1080p", "720p", "4K", "1080p"][index % 4],
            "image_mode": "Preto e branco" if index % 5 == 0 else "Colorida",
            "ptz": index % 2 == 0,
        }
    if typ == "balanca":
        return {"capacity_tons": 40, "axles": 5}
    if typ == "veiculo_autonomo":
        return {"plate": f"RAT{index}B{10+index}", "range_km": 90, "autonomy_hours": 8}
    if typ == "cancela":
        return {"direction": ["Entrada", "Saída", "Ambos"][index % 3], "linked_place": "Pátio rotativo"}
    if typ == "transporte":
        cat = ["Táxi", "Mototáxi", "Escolar"][index % 3]
        seats = {"Táxi": 4, "Mototáxi": 1, "Escolar": 16}[cat]
        return {
            "category": cat,
            "plate": f"QXT{index}C{20+index}",
            "license": f"ALV-{4000+index}",
            "seats": seats,
            "in_service": cat != "Escolar",
        }
    if typ == "totem":
        return {"payments": "Pix, cartão e dinheiro", "spots": 40 + (index % 5) * 20}
    if typ == "patinete":
        return {"fleet_size": 8 + (index % 6), "avg_battery": 70, "operator": "Giro"}
    if typ == "moto_agente":
        return {"plate": f"MOT{index}D{30+index}", "prefix": f"M-{200+index}"}
    if typ == "viatura_gm":
        return {"plate": f"GM{index}E{40+index}", "prefix": f"GM-{10+index}", "unit": "Ronda urbana"}
    if typ == "viatura_pm":
        return {"plate": f"PM{index}F{50+index}", "prefix": f"PM-{300+index}", "unit": "1º BPRv"}
    return {}


def _place(eq: dict, region: str, rng: random.Random, meters: float = 500) -> None:
    meta = REGIONS[region]
    lat, lng = _jitter(rng, meta["lat"], meta["lng"], meters)
    street = rng.choice(STREETS[region])
    eq.update({
        "region": region,
        "neighborhood": rng.choice(NEIGHBORHOODS[region]),
        "city": meta["city"],
        "uf": meta["uf"],
        "cep": _cep(rng, meta["cep_prefix"]),
        "street": street,
        "reference": _reference(rng, street),
        "lat": lat,
        "lng": lng,
    })


def _stamp_place(eq: dict, region: str, **overrides: Any) -> None:
    meta = REGIONS[region]
    eq["region"] = region
    eq["city"] = meta["city"]
    eq["uf"] = meta["uf"]
    for key, value in overrides.items():
        eq[key] = value


# ---------- histórico ----------

def _build_history(rng: random.Random, today: date) -> dict[str, Any]:
    buckets: dict[str, list[int]] = {}
    daily = []
    start = today - timedelta(days=HISTORY_DAYS)
    for i in range(HISTORY_DAYS):
        day = start + timedelta(days=i)
        if day >= today:
            break
        dow = day.weekday()
        total = 0
        by_region: dict[str, int] = {}
        for region in REGIONS:
            region_total = 0
            for hour in range(24):
                lam = lambda_of(region, dow, hour, i)
                count = noisy_count(rng, lam)
                buckets.setdefault(_bucket_key(region, dow, hour), []).append(count)
                region_total += count
            by_region[region] = region_total
            total += region_total
        daily.append({"date": day.isoformat(), "count": total, "by_region": by_region})

    availability = []
    for i in range(29, -1, -1):
        day = today - timedelta(days=i)
        pct = 93.0
        if 12 >= i >= 10:
            pct = 76.0
        elif i == 13 or i == 9:
            pct = 84.0
        availability.append({"date": day.isoformat(), "pct": pct})

    return {"buckets": buckets, "daily": daily, "availability": availability}


def _series(today: date, values: list[float]) -> list[dict[str, Any]]:
    start = today - timedelta(days=len(values) - 1)
    return [{"date": (start + timedelta(days=i)).isoformat(), "value": values[i]} for i in range(len(values))]


# ---------- cidade inicial ----------

def build_demo(moment: datetime | None = None) -> dict[str, Any]:
    moment = moment or now_local()
    today = moment.date()
    rng = random.Random(SEED)
    data: dict[str, Any] = {
        "meta": {
            "seed": SEED,
            "schema": SCHEMA,
            "created_at": iso(moment),
            "next_equipment": 1001,
            "next_agent": 1001,
            "next_incident": 3001,
            "next_feed": 1,
            "tick": 0,
        },
        "equipment": [],
        "agents": [],
        "incidents": [],
        "feed": [],
        "history": _build_history(rng, today),
    }
    _build_equipment(data, rng, today, moment)
    _build_agents(data, rng, moment)
    _pair(data)
    _plant_anomaly(data, moment)
    _build_utilization(data, today)
    _seed_feed(data, moment, today)
    _seed_operations(data, moment)
    return data


def _next_id(data: dict, kind: str, prefix: str) -> str:
    key = f"next_{kind}"
    number = data["meta"][key]
    data["meta"][key] = number + 1
    return f"{prefix}-{number}"


def _build_equipment(data: dict, rng: random.Random, today: date, moment: datetime) -> None:
    plan = [
        ("radar", 8), ("camera", 12), ("balanca", 3), ("veiculo_autonomo", 3),
        ("cancela", 4), ("transporte", 8), ("totem", 4), ("patinete", 5),
        ("moto_agente", 5), ("viatura_gm", 4), ("viatura_pm", 4),
    ]
    regions = list(REGIONS)
    cursor = 0
    index = 0
    for typ, count in plan:
        for _ in range(count):
            region = regions[cursor % len(regions)]
            cursor += 1
            brand, model = BRANDS[typ][index % len(BRANDS[typ])]
            agency = _agency_for(typ, index)
            installed = today - timedelta(days=rng.randint(200, 2800))
            eq = {
                "id": _next_id(data, "equipment", "EQ"),
                "type": typ,
                "serial": f"{PREFIX[typ]}-{1000 + index}",
                "brand": brand,
                "model": model,
                "agency": agency,
                "status": "operacional",
                "maintenance_need": "agendada",
                "next_maintenance": (today + timedelta(days=rng.randint(25, 110))).isoformat(),
                "installed_at": installed.isoformat(),
                "notes": "",
                "attrs": _default_attrs(typ, index),
                "last_seen": iso(moment),
                "created_at": iso(moment),
                "updated_at": iso(moment),
            }
            _place(eq, region, rng)
            data["equipment"].append(eq)
            index += 1
    _apply_stories(data["equipment"], today, moment)


def ensure_inventory_size(data: dict, moment: datetime) -> bool:
    if len(data.get("equipment") or []) >= 60:
        return False
    rng = random.Random(SEED + 91)
    today = moment.date()
    cycle = ["radar", "camera", "balanca", "transporte", "totem", "patinete", "moto_agente", "viatura_gm", "viatura_pm", "cancela", "veiculo_autonomo"]
    regions = list(REGIONS)
    taken = {item.get("serial") for item in data["equipment"]}
    data["meta"].setdefault("next_equipment", len(data["equipment"]) + 1)
    index = len(data["equipment"])
    while len(data["equipment"]) < 60:
        typ = cycle[index % len(cycle)]
        brand, model_name = BRANDS[typ][index % len(BRANDS[typ])]
        serial = f"{PREFIX[typ]}-{2000 + index}"
        while serial in taken:
            index += 1
            serial = f"{PREFIX[typ]}-{2000 + index}"
        taken.add(serial)
        eq = {
            "id": _next_id(data, "equipment", "EQ"),
            "type": typ,
            "serial": serial,
            "brand": brand,
            "model": model_name,
            "agency": _agency_for(typ, index),
            "status": "operacional",
            "maintenance_need": "agendada",
            "next_maintenance": (today + timedelta(days=40 + (index % 50))).isoformat(),
            "installed_at": (today - timedelta(days=400 + index)).isoformat(),
            "notes": "Incluído para completar o inventário de demonstração.",
            "attrs": _default_attrs(typ, index),
            "last_seen": iso(moment),
            "created_at": iso(moment),
            "updated_at": iso(moment),
            "history": [],
        }
        _place(eq, regions[index % len(regions)], rng)
        data["equipment"].append(eq)
        index += 1
    return True


def _agency_for(typ: str, index: int) -> str:
    if typ in ("viatura_gm", "moto_agente"):
        return "Guarda Municipal" if typ == "viatura_gm" else "Secretaria de Mobilidade"
    if typ == "viatura_pm":
        return "Polícia Militar"
    if typ == "transporte":
        return "Permissionário de transporte"
    if typ == "patinete":
        return "Operador de micromobilidade"
    if typ == "balanca":
        return "DETRAN/SP"
    return "Secretaria de Mobilidade"


def _find(items: list[dict], typ: str, region: str | None = None) -> dict:
    for eq in items:
        if eq.get("_claimed"):
            continue
        if eq["type"] != typ:
            continue
        if region and eq["region"] != region:
            continue
        eq["_claimed"] = True
        return eq
    for eq in items:
        if not eq.get("_claimed") and eq["type"] == typ:
            eq["_claimed"] = True
            return eq
    raise RuntimeError(f"não há equipamento livre do tipo {typ}")


def _apply_stories(items: list[dict], today: date, moment: datetime) -> None:
    beira = _find(items, "radar", "Centro Marília")
    _stamp_place(
        beira, "Centro Marília",
        neighborhood="Centro", street="Avenida Rio Branco",
        reference="oposto ao número 181", cep="17500-020",
        lat=-22.2134, lng=-49.9466,
    )
    beira.update({
        "serial": "RAD-RIOBRANCO", "brand": "Velsis", "model": "Velox R-310",
        "status": "operacional", "maintenance_need": "agendada",
        "next_maintenance": (today + timedelta(days=3)).isoformat(),
        "notes": "Corredor do centro de Marília. Manutenção periódica em três dias: confirmar equipe antes do fim de semana.",
        "attrs": {"radar_kind": "Velocidade", "speed_limit": 60, "lanes": 2},
    })

    ponte = _find(items, "radar", "Sampaio Vidal")
    _stamp_place(
        ponte, "Sampaio Vidal",
        neighborhood="Sampaio Vidal", street="Avenida Sampaio Vidal",
        reference="em frente ao terminal", cep="17509-020",
        lat=-22.2171, lng=-49.9648,
    )
    ponte.update({
        "serial": "RAD-SAMPAIO", "brand": "Perkons", "model": "Pardal Compact",
        "status": "mau_funcionamento", "maintenance_need": "imediata",
        "next_maintenance": today.isoformat(),
        "notes": "Parou de fiscalizar a Sampaio Vidal. As leituras do histórico caem a zero a partir da falha.",
        "attrs": {"radar_kind": "Velocidade", "speed_limit": 50, "lanes": 3},
        "last_seen": iso(moment - timedelta(minutes=42)),
    })

    catedral = _find(items, "camera", "Centro Marília")
    _stamp_place(
        catedral, "Centro Marília",
        neighborhood="Centro", street="Rua São Luiz",
        reference="em frente à Catedral de São Bento", cep="17500-100",
        lat=-22.2148, lng=-49.9452,
    )
    catedral.update({
        "serial": "CAM-CENTRO", "brand": "Axis", "model": "P3265",
        "status": "operacional", "maintenance_need": "agendada",
        "next_maintenance": (today + timedelta(days=48)).isoformat(),
        "notes": "Câmera estável do centro de Marília. Serve de contraste: nem toda série pede ação.",
        "attrs": {"night_vision": True, "resolution": "1080p", "image_mode": "Colorida", "ptz": True},
    })

    furto = _find(items, "camera", "Vila Xavier")
    _stamp_place(
        furto, "Vila Xavier",
        neighborhood="Vila Xavier", street="Rua Paraná",
        reference="número 2400", cep="19806-100",
        lat=-22.6492, lng=-50.3968,
    )
    furto.update({
        "serial": "CAM-XAVIER", "brand": "Intelbras", "model": "VIP 3240",
        "status": "furtado", "maintenance_need": "nenhuma", "next_maintenance": None,
        "notes": "Ponto cego em Assis. A Vila Xavier perde videomonitoramento até a reposição.",
        "attrs": {"night_vision": True, "resolution": "1080p", "image_mode": "Colorida", "ptz": False},
    })

    atraso = _find(items, "camera", "Fragata")
    _stamp_place(
        atraso, "Fragata",
        neighborhood="Fragata", street="Avenida República",
        reference="número 540", cep="17519-310",
        lat=-22.2062, lng=-49.9774,
    )
    atraso.update({
        "serial": "CAM-FRAGATA", "brand": "Hikvision", "model": "DS-2CD",
        "status": "operacional", "maintenance_need": "agendada",
        "next_maintenance": (today - timedelta(days=2)).isoformat(),
        "installed_at": (today - timedelta(days=2900)).isoformat(),
        "notes": "Ainda transmite, mas a revisão periódica venceu. É o caso que quebra sem um alarme novo.",
        "attrs": {"night_vision": False, "resolution": "720p", "image_mode": "Colorida", "ptz": False},
    })

    off = _find(items, "camera")
    off.update({
        "serial": "CAM-DESATIVADA",
        "status": "desativado", "maintenance_need": "nenhuma", "next_maintenance": None,
        "notes": "Desligada de propósito após obra. Não entra na disponibilidade como pane.",
    })

    balanca = _find(items, "balanca", "Cândido Mota")
    _stamp_place(
        balanca, "Cândido Mota",
        neighborhood="Centro", street="SP-333",
        reference="KM 12", cep="19880-000",
        lat=-22.7510, lng=-50.3910,
    )
    balanca.update({
        "serial": "BAL-MOTA", "brand": "Toledo", "model": "Guardião 950",
        "agency": "DETRAN/SP",
        "status": "mau_funcionamento", "maintenance_need": "imediata",
        "next_maintenance": today.isoformat(),
        "notes": "Aferição recusando pesagem. Caminhões seguem sem controle neste KM da SP-333.",
        "attrs": {"capacity_tons": 40, "axles": 6},
        "last_seen": iso(moment - timedelta(minutes=25)),
    })

    auto = _find(items, "veiculo_autonomo", "Centro Marília")
    auto.update({
        "serial": "VAF-CENTRO",
        "status": "em_manutencao", "maintenance_need": "agendada",
        "next_maintenance": (today + timedelta(days=1)).isoformat(),
        "notes": "Na oficina. A rota do rotativo do centro de Marília está descoberta até amanhã.",
    })

    totem = _find(items, "totem", "Alto Cafezal")
    totem.update({
        "serial": "TOT-CAFEZAL",
        "status": "ainda_nao_instalado", "maintenance_need": "nenhuma",
        "next_maintenance": None, "installed_at": None, "last_seen": None,
        "notes": "Previsto para o novo bolsão do Alto Cafezal. Já entra no inventário para a obra não se perder.",
    })

    pat = _find(items, "patinete", "Campus")
    _stamp_place(
        pat, "Campus",
        neighborhood="Campus Universitário", street="Avenida Hygino Muzy Filho",
        reference="em frente à UNESP", cep="17525-900",
        lat=-22.2304, lng=-49.9340,
    )
    pat.update({
        "serial": "PAT-CAMPUS", "brand": "Giro", "model": "Hub Giro",
        "status": "operacional",
        "notes": "O ponto opera, mas as viagens caem há duas semanas. Olhar bateria e redistribuição antes de tratar como pane.",
        "attrs": {"fleet_size": 16, "avg_battery": 61, "operator": "Giro"},
    })

    for eq in items:
        eq.pop("_claimed", None)


def _build_agents(data: dict, rng: random.Random, moment: datetime) -> None:
    agencies = (["Secretaria de Mobilidade"] * 10 + ["Guarda Municipal"] * 8 + ["Polícia Militar"] * 6)
    roles = {
        "Secretaria de Mobilidade": "Agente de trânsito",
        "Guarda Municipal": "Guarda municipal",
        "Polícia Militar": "Policial militar",
    }
    prefixes = {"Secretaria de Mobilidade": "AT", "Guarda Municipal": "GM", "Polícia Militar": "PM"}
    counts = {"AT": 2401, "GM": 3101, "PM": 1041}
    regions = list(REGIONS)
    for i, name in enumerate(PEOPLE):
        region = regions[i % 8]
        shift = SHIFTS[i // 8]
        agency = agencies[i]
        prefix = prefixes[agency]
        reg = f"{prefix}-{counts[prefix]}"
        counts[prefix] += 1
        meta = REGIONS[region]
        lat, lng = _jitter(rng, meta["lat"], meta["lng"], 400)
        street = rng.choice(STREETS[region])
        role = "Supervisor de campo" if i % 8 == 0 else roles[agency]
        agent = {
            "id": _next_id(data, "agent", "AG"),
            "name": name,
            "registration": reg,
            "agency": agency,
            "role": role,
            "shift": shift,
            "status": "fora_de_servico",
            "phone": f"(14) 9{rng.randint(1000, 9999)}-{rng.randint(1000, 9999)}",
            "team": TEAMS[region],
            "region": region,
            "base_region": region,
            "neighborhood": rng.choice(NEIGHBORHOODS[region]),
            "city": meta["city"],
            "uf": meta["uf"],
            "cep": _cep(rng, meta["cep_prefix"]),
            "street": street,
            "reference": _reference(rng, street),
            "lat": lat,
            "lng": lng,
            "base_lat": lat,
            "base_lng": lng,
            "paired_equipment_id": None,
            "notes": "",
            "last_seen": iso(moment),
            "created_at": iso(moment),
            "updated_at": iso(moment),
        }
        data["agents"].append(agent)
    _assign_statuses(data["agents"], moment.hour)


def _assign_statuses(agents: list[dict], hour: int) -> None:
    current = shift_of(hour)
    paused = False
    moving = False
    for agent in agents:
        if agent["shift"] != current:
            agent["status"] = "fora_de_servico"
            continue
        if agent["base_region"] == "Campus" and not paused:
            agent["status"] = "em_pausa"
            paused = True
        elif agent["base_region"] == "Centro Marília" and not moving:
            agent["status"] = "em_deslocamento"
            moving = True
        else:
            agent["status"] = "em_atividade"


def _pair(data: dict) -> None:
    used: set[str] = set()
    for eq in data["equipment"]:
        if eq["type"] not in ("moto_agente", "viatura_gm", "viatura_pm"):
            continue
        same = [
            a for a in data["agents"]
            if a["id"] not in used and a["base_region"] == eq["region"] and a["agency"] == eq["agency"]
        ]
        if not same:
            same = [a for a in data["agents"] if a["id"] not in used and a["base_region"] == eq["region"]]
        if not same:
            continue
        agent = same[0]
        agent["paired_equipment_id"] = eq["id"]
        eq["attrs"]["paired_agent_id"] = agent["id"]
        used.add(agent["id"])
        eq["lat"], eq["lng"] = agent["base_lat"], agent["base_lng"]


def _plant_anomaly(data: dict, moment: datetime) -> None:
    region = "Sampaio Vidal"
    mean, std, _, _, _ = bucket_stats(data, region, moment.weekday(), moment.hour)
    target_rate = max(0.9, mean * 2)
    target = math.ceil(target_rate * ANOMALY_WINDOW_H)
    target = min(8, max(4, target))
    titles = [
        "Congestionamento no corredor da Sampaio Vidal",
        "Fila parada no acesso à avenida",
        "Veículo quebrado reduzindo uma faixa",
        "Fluxo travado depois do radar inoperante",
        "Buzinaço e retorno improvisado na avenida",
        "Acúmulo de veículos no corredor",
        "Condutor em contramão para fugir da fila",
        "Pedestre cruzando fora da faixa no engarrafamento",
    ]
    for i in range(target):
        lat, lng = _jitter(random.Random(SEED + i), -22.2171, -49.9648, 280)
        incident = {
            "id": _next_id(data, "incident", "OC"),
            "kind": "congestionamento",
            "severity": "media",
            "status": "aberto",
            "analytical": True,
            "title": titles[i % len(titles)],
            "detail": "Registro do corredor da Sampaio Vidal. Sozinho seria rotina; junto com os outros, sai do padrão da hora.",
            "region": region,
            "lat": lat,
            "lng": lng,
            "at": iso(moment - timedelta(minutes=12 + i * 18)),
        }
        data["incidents"].append(incident)


def _build_utilization(data: dict, today: date) -> None:
    by_serial = {eq["serial"]: eq["id"] for eq in data["equipment"]}
    radar = [128, 121, 134, 126, 119, 130, 124, 8, 0, 0, 0, 0, 0, 0]
    scooters = [82, 80, 79, 76, 74, 73, 71, 69, 66, 64, 63, 61, 59, 57]
    cameras = [99, 98, 99, 97, 99, 98, 99, 98, 99, 97, 99, 98, 99, 98]
    data["history"]["utilization"] = [
        {
            "id": "util-radar",
            "title": "Leituras do radar da Sampaio Vidal",
            "unit": "leituras/dia",
            "equipment_id": by_serial.get("RAD-SAMPAIO"),
            "points": _series(today, radar),
        },
        {
            "id": "util-pat",
            "title": "Viagens no ponto de patinetes da UNESP",
            "unit": "viagens/dia",
            "equipment_id": by_serial.get("PAT-CAMPUS"),
            "points": _series(today, scooters),
        },
        {
            "id": "util-cam",
            "title": "Disponibilidade da câmera da catedral",
            "unit": "% do dia no ar",
            "equipment_id": by_serial.get("CAM-CENTRO"),
            "points": _series(today, cameras),
        },
    ]


SHIFT_KIND = {
    "entrada": "Entrada",
    "saida": "Saída",
    "intervalo": "Intervalo",
    "retorno": "Retorno",
}


def record_shift(data: dict, payload: dict, moment: datetime, actor: str) -> dict[str, Any]:
    kind = _choice(payload.get("kind"), "o registro", list(SHIFT_KIND))
    agent = _must(data["agents"], str(payload.get("agent_id") or ""), "Agente")
    data["meta"].setdefault("next_event", 1)
    item = {
        "id": _next_id(data, "event", "EV"),
        "kind": kind,
        "label": SHIFT_KIND[kind],
        "agent_id": agent["id"],
        "agent_name": agent["name"],
        "team": agent.get("team") or "",
        "region": agent.get("region") or "",
        "lat": agent.get("lat"),
        "lng": agent.get("lng"),
        "at": iso(moment),
        "origin": "central",
        "actor": actor,
    }
    data.setdefault("events", []).insert(0, item)
    del data["events"][200:]
    push_feed(data, "info", f"{agent['name']} registrou {SHIFT_KIND[kind].lower()}.", item["region"], moment)
    return {"message": f"{SHIFT_KIND[kind]} registrada para {agent['name']}.", "focus": {"kind": "agent", "id": agent["id"]}}


def push_feed(data: dict, level: str, text: str, region: str, moment: datetime) -> dict:
    item = {
        "id": f"FD-{data['meta']['next_feed']}",
        "level": level,
        "text": text,
        "region": region,
        "at": iso(moment),
    }
    data["meta"]["next_feed"] += 1
    data["feed"].insert(0, item)
    del data["feed"][50:]
    return item


def _seed_feed(data: dict, moment: datetime, today: date) -> None:
    stories = [
        ("critico", "Câmera CAM-XAVIER marcada como furtada na Rua Paraná, em Assis.", "Vila Xavier", moment - timedelta(hours=5)),
        ("critico", "Radar RAD-SAMPAIO entrou em mau funcionamento na Avenida Sampaio Vidal.", "Sampaio Vidal", moment - timedelta(minutes=50)),
        ("critico", "Balança BAL-MOTA no KM 12 da SP-333 parou de aferir.", "Cândido Mota", moment - timedelta(minutes=30)),
        ("atencao", "Câmera da Fragata segue no ar com a revisão periódica atrasada.", "Fragata", moment - timedelta(hours=3)),
        ("atencao", "Radar da Rio Branco tem manutenção marcada para daqui a três dias.", "Centro Marília", moment - timedelta(hours=2)),
    ]
    for level, text, region, when in stories:
        push_feed(data, level, text, region, when)
    for incident in data["incidents"]:
        push_feed(data, "atencao", incident["title"] + " · Sampaio Vidal.", "Sampaio Vidal", parse_iso(incident["at"]))
    data["feed"].sort(key=lambda item: item["at"], reverse=True)


# ---------- indicadores, anomalia, previsão ----------

def kpis(data: dict) -> dict[str, Any]:
    by = Counter(eq["status"] for eq in data["equipment"])
    total = len(data["equipment"])
    not_installed = by["ainda_nao_instalado"]
    operational = by["operacional"]
    unavailable = sum(by[name] for name in UNAVAILABLE)
    installed = total - not_installed
    availability = round(100 * operational / installed, 1) if installed else 0.0
    active = sum(1 for agent in data["agents"] if agent["status"] in ACTIVE_AGENT)
    return {
        "total": total,
        "operational": operational,
        "unavailable": unavailable,
        "not_installed": not_installed,
        "installed": installed,
        "availability_pct": availability,
        "agents_total": len(data["agents"]),
        "agents_active": active,
        "by_status": {key: by.get(key, 0) for key, _ in EQUIPMENT_STATUSES},
    }


def sensor_factor(data: dict, region: str) -> tuple[float, list[dict], list[dict]]:
    sensors = [
        eq for eq in data["equipment"]
        if eq["region"] == region and eq["type"] in SENSOR_TYPES and eq["status"] != "ainda_nao_instalado"
    ]
    down = [eq for eq in sensors if eq["status"] in BAD_STATUS]
    if not sensors:
        return 1.0, [], []
    factor = 1 + 0.45 * (len(down) / len(sensors))
    return min(1.25, factor), down, sensors


def _agents_for(data: dict, region: str, hour: int, mode: str) -> list[dict]:
    if mode == "live":
        return [a for a in data["agents"] if a["region"] == region and a["status"] in ACTIVE_AGENT]
    shift = shift_of(hour)
    return [a for a in data["agents"] if a["base_region"] == region and a["shift"] == shift]


def coverage_need(baseline: float) -> int:
    if baseline < 0.4:
        return 0
    return max(1, math.ceil(baseline / CAPACITY))


def region_hour(data: dict, region: str, moment: datetime, mode: str) -> dict[str, Any]:
    mean, std, samples, recent, blended = bucket_stats(data, region, moment.weekday(), moment.hour)
    factor, down, sensors = sensor_factor(data, region)
    adjusted = blended * factor
    ipo = int(round(min(100, 100 * adjusted / REF_IPO)))
    level, label = level_of(ipo)
    agents = _agents_for(data, region, moment.hour, mode)
    need = coverage_need(blended * factor)
    have = len(agents)
    gap = max(0, need - have)
    return {
        "region": region,
        "hour": moment.hour,
        "mean": round(mean, 2),
        "std": round(std, 2),
        "samples": samples,
        "recent": round(recent, 2),
        "blended": round(blended, 2),
        "equip_factor": round(factor, 3),
        "sensors_down": len(down),
        "sensors_total": len(sensors),
        "sensor_names": [eq["serial"] for eq in down],
        "adjusted": round(adjusted, 2),
        "ipo": ipo,
        "level": level,
        "level_label": label,
        "have": have,
        "need": need,
        "gap": gap,
        "lat": REGIONS[region]["lat"],
        "lng": REGIONS[region]["lng"],
        "city": REGIONS[region]["city"],
    }


def _mode_for(moment: datetime, real_now: datetime) -> str:
    if moment.date() == real_now.date() and moment.hour == real_now.hour:
        return "live"
    return "plan"


def anomaly_stats(count: int, mean: float, std: float, window_h: float = ANOMALY_WINDOW_H) -> dict[str, Any]:
    rate = count / window_h
    z = (rate - mean) / max(std, 0.35)
    unusual = count >= 3 and (z >= 2 or rate >= max(0.9, mean * 2))
    return {
        "count": count,
        "rate": round(rate, 2),
        "mean": round(mean, 2),
        "std": round(std, 2),
        "z": round(z, 2),
        "unusual": unusual,
        "window_h": window_h,
    }


def anomalies(data: dict, moment: datetime) -> list[dict[str, Any]]:
    found = []
    window_start = moment - timedelta(hours=ANOMALY_WINDOW_H)
    for region in REGIONS:
        count = 0
        for incident in data["incidents"]:
            if incident["region"] != region or not incident.get("analytical"):
                continue
            if incident["status"] != "aberto":
                continue
            if parse_iso(incident["at"]) >= window_start:
                count += 1
        mean, std, _, _, _ = bucket_stats(data, region, moment.weekday(), moment.hour)
        stats = anomaly_stats(count, mean, std)
        if not stats["unusual"]:
            continue
        found.append({
            "region": region,
            **stats,
            "title": f"Possível evento operacional em {region}",
            "detail": (
                f"{count} ocorrências analíticas em {ANOMALY_WINDOW_H} horas "
                f"(ritmo de {fmt_num(stats['rate'])} por hora). "
                f"A média histórica desta hora é {fmt_num(stats['mean'])}, "
                f"com desvio {fmt_num(stats['std'])}. Escore z {fmt_num(stats['z'])}."
            ),
        })
    found.sort(key=lambda item: item["z"], reverse=True)
    return found


def derive_alerts(data: dict, moment: datetime) -> list[dict[str, Any]]:
    today = moment.date()
    found_anomalies = anomalies(data, moment)
    anomalous_regions = {item["region"] for item in found_anomalies}
    alerts: list[dict[str, Any]] = []

    for eq in data["equipment"]:
        flag = maintenance_flag(eq, today)
        level = None
        title = ""
        detail = ""
        if eq["status"] == "furtado":
            level = "critico"
            title = f"{eq['serial']} furtado"
            detail = f"{TYPES[eq['type']]['label']} em {eq['street']}, {eq['neighborhood']}. O ponto está cego."
        elif eq["status"] == "mau_funcionamento":
            level = "critico"
            title = f"{eq['serial']} em mau funcionamento"
            detail = f"{eq['street']}, {eq['neighborhood']}. Manutenção imediata."
        elif flag == "imediata":
            level = "atencao"
            title = f"Manutenção imediata · {eq['serial']}"
            detail = f"{eq['street']}, {eq['region']}."
        elif eq["status"] == "em_manutencao":
            level = "atencao"
            title = f"{eq['serial']} está na oficina"
            detail = "Fora da rua até o cadastro voltar a operacional."
        elif flag == "atrasada":
            level = "atencao"
            title = f"Manutenção atrasada · {eq['serial']}"
            detail = f"A data prevista era {eq.get('next_maintenance')} e o equipamento segue em campo."
        elif flag == "proxima":
            level = "atencao"
            title = f"Manutenção em breve · {eq['serial']}"
            detail = f"Próxima data {eq.get('next_maintenance')} em {eq['neighborhood']}."
        if level:
            alerts.append({
                "id": f"eq-{eq['id']}",
                "level": level,
                "title": title,
                "detail": detail,
                "region": eq["region"],
                "target_type": "equipment",
                "target_id": eq["id"],
                "at": eq.get("updated_at") or eq.get("created_at"),
            })

    for incident in data["incidents"]:
        if incident["status"] != "aberto":
            continue
        if incident["severity"] == "baixa":
            continue
        if incident["severity"] == "media" and incident["region"] in anomalous_regions:
            continue
        level = "critico" if incident["severity"] == "alta" else "atencao"
        alerts.append({
            "id": f"inc-{incident['id']}",
            "level": level,
            "title": incident["title"],
            "detail": incident["detail"],
            "region": incident["region"],
            "target_type": "incident",
            "target_id": incident["id"],
            "at": incident["at"],
        })

    for item in found_anomalies:
        alerts.append({
            "id": f"an-{item['region']}",
            "level": "critico",
            "title": item["title"],
            "detail": item["detail"],
            "region": item["region"],
            "target_type": "region",
            "target_id": item["region"],
            "at": iso(moment),
        })

    for region in REGIONS:
        live = region_hour(data, region, moment, "live")
        if live["gap"] >= 1 and live["blended"] >= 0.8 and live["ipo"] >= 50:
            alerts.append({
                "id": f"cov-{region}",
                "level": "atencao",
                "title": f"Cobertura curta em {region}",
                "detail": (
                    f"Há {live['have']} agente(s) em campo e a hora pede {live['need']}. "
                    f"IPO {live['ipo']}."
                ),
                "region": region,
                "target_type": "region",
                "target_id": region,
                "at": iso(moment),
            })

    order = {"critico": 0, "atencao": 1, "info": 2}
    alerts.sort(key=lambda item: (order.get(item["level"], 9), item["title"]))
    return alerts


def _sentence(index: int, band_label: str, hot: dict, alerts: list[dict]) -> str:
    critical = [a for a in alerts if a["level"] == "critico"]
    if critical and hot["ipo"] < 45:
        if hot["ipo"] < 15:
            quiet = "Nenhuma região acumula pressão nesta hora."
        else:
            quiet = f"O maior IPO agora é {hot['region']} ({hot['ipo']}), ainda em faixa calma."
        return (
            f"A cidade está em {band_label} ({index}). {quiet} "
            f"O que segura o índice são {len(critical)} alertas críticos ainda abertos."
        )
    parts = [f"A cidade está em {band_label} ({index}). Maior pressão agora: {hot['region']} (IPO {hot['ipo']})."]
    if critical:
        parts.append(f"{len(critical)} alerta(s) crítico(s) pedem ação antes do resto da fila.")
    else:
        parts.append("Nenhum alerta crítico aberto neste instante.")
    return " ".join(parts)


def city_index(data: dict, moment: datetime, alerts: list[dict] | None = None) -> dict[str, Any]:
    alerts = derive_alerts(data, moment) if alerts is None else alerts
    lives = [region_hour(data, region, moment, "live") for region in REGIONS]
    hot = max(lives, key=lambda item: (item["ipo"], item["gap"]))
    mean_ipo = sum(item["ipo"] for item in lives) / len(lives)
    n_crit = sum(1 for a in alerts if a["level"] == "critico")
    value = int(round(min(100, 0.7 * hot["ipo"] + 0.3 * mean_ipo)))
    if n_crit:
        value = min(100, value + min(18, 4 * n_crit))
    level, label = level_of(value)
    if n_crit >= 3 and value < 50:
        level, label = "pressao", "pressão"
        value = max(value, 55)
    return {
        "value": value,
        "band": level,
        "label": label,
        "hot_region": hot["region"],
        "hot_ipo": hot["ipo"],
        "sentence": _sentence(value, label, hot, alerts),
        "regions": lives,
    }


def _delta(points: list[dict]) -> float | None:
    if len(points) < 8:
        return None
    half = len(points) // 2
    first = [p["value"] for p in points[:half]]
    last = [p["value"] for p in points[half:]]
    a = sum(first) / len(first)
    b = sum(last) / len(last)
    if a == 0:
        return None
    return round(100 * (b - a) / a, 1)


def equipment_risks(data: dict, today: date) -> list[dict[str, Any]]:
    rows = []
    for eq in data["equipment"]:
        if eq["status"] in ("desativado", "ainda_nao_instalado"):
            continue
        score = 8
        reasons = []
        horizon = "próximos 7 dias"
        if eq["status"] == "mau_funcionamento":
            score += 62
            horizon = "próximas horas"
            reasons.append("Já está em mau funcionamento. Sem manutenção, segue fora amanhã de manhã.")
        elif eq["status"] == "furtado":
            score += 70
            horizon = "até a reposição"
            reasons.append("A ausência já é fato. O risco não é falhar: é continuar cego.")
        elif eq["status"] == "em_manutencao":
            score += 34
            horizon = "até a baixa da oficina"
            reasons.append("Na manutenção. Não conta como recurso do dia projetado.")
        flag = maintenance_flag(eq, today)
        if flag == "atrasada" and eq["status"] == "operacional":
            score += 30
            reasons.append("A revisão periódica venceu e ele ainda opera. É o perfil que para sem aviso novo.")
        elif flag == "proxima" and eq["status"] == "operacional":
            score += 16
            reasons.append("A próxima manutenção cai em até 7 dias. Confirmar equipe e peça antes da data.")
        elif flag == "imediata" and eq["status"] == "operacional":
            score += 40
            reasons.append("Há pedido de manutenção imediata com status ainda operacional.")
        if eq.get("installed_at") and eq["status"] == "operacional":
            years = (today - date.fromisoformat(eq["installed_at"])).days / 365
            if years >= 7:
                score += 8
                reasons.append(f"Em campo há {int(years)} anos. A idade soma pouco, e só junto com outro sinal.")
        if score < 20:
            continue
        rows.append({
            "id": eq["id"],
            "serial": eq["serial"],
            "type": eq["type"],
            "label": TYPES[eq["type"]]["label"],
            "region": eq["region"],
            "street": eq["street"],
            "score": min(96, score),
            "horizon": horizon,
            "reasons": reasons,
            "status": eq["status"],
        })
    rows.sort(key=lambda item: item["score"], reverse=True)
    return rows[:8]


def _utilization_view(data: dict) -> list[dict[str, Any]]:
    views = []
    by_id = {eq["id"]: eq for eq in data["equipment"]}
    for series in data["history"].get("utilization", []):
        delta = _delta(series["points"])
        eq = by_id.get(series.get("equipment_id"))
        note = _utilization_note(series["id"], delta, eq)
        views.append({
            "id": series["id"],
            "title": series["title"],
            "unit": series["unit"],
            "equipment_id": series.get("equipment_id"),
            "points": series["points"],
            "delta_pct": delta,
            "note": note,
        })
    return views


def _utilization_note(series_id: str, delta: float | None, eq: dict | None) -> str:
    if delta is None:
        return "Série curta demais para ler tendência."
    if series_id == "util-radar":
        return (
            f"Queda de {fmt_num(abs(delta))}% entre a primeira e a segunda metade da quinzena, "
            "com as leituras indo a zero. No cadastro este radar está em mau funcionamento: "
            "a série confirma a perda e dá a medida do que a Sampaio Vidal deixa de fiscalizar por dia."
        )
    if series_id == "util-pat":
        status = "operacional" if eq and eq["status"] == "operacional" else "indisponível"
        return (
            f"Queda de {fmt_num(abs(delta))}% nas viagens, com o ponto ainda {status}. "
            "Não trate como pane. Vale checar carga, redistribuição da frota e o movimento do campus antes de recolher o hub."
        )
    return (
        "Série estável. Nenhuma ação além da manutenção que já está agendada. "
        "Serve para não tratar todo gráfico como alarme."
    )


def _availability_view(data: dict, today: date) -> dict[str, Any]:
    series = [dict(point) for point in data["history"]["availability"]]
    actual = kpis(data)["availability_pct"]
    if series:
        series[-1] = {"date": today.isoformat(), "pct": actual}
    return {
        "points": series,
        "note": (
            "No histórico carregado, a disponibilidade caiu para a faixa dos 76% por três dias e se recuperou. "
            f"O último ponto não é estimativa: é a conta de agora, {fmt_num(actual)}% dos equipamentos já instalados."
        ),
    }


def _incident_trend_note(daily: list[dict]) -> str:
    if len(daily) < 40:
        return "Histórico curto demais para ler uma deriva."
    first = daily[:14]
    last = daily[-14:]
    notes = []
    for region in REGIONS:
        a = sum(day["by_region"].get(region, 0) for day in first) / 14
        b = sum(day["by_region"].get(region, 0) for day in last) / 14
        if a <= 0:
            continue
        delta = 100 * (b - a) / a
        if abs(delta) >= 15:
            direction = "acima" if delta > 0 else "abaixo"
            notes.append(f"{region} está {fmt_num(abs(delta))}% {direction} do começo do histórico")
    if not notes:
        return (
            "Nenhuma região desviou 15% ou mais entre o começo e o fim do histórico. "
            "O movimento cabe no perfil de dia útil e fim de semana."
        )
    return (
        "Isto não é o salto de uma semana para a outra. Comparando as primeiras duas semanas do histórico com as últimas: "
        + "; ".join(notes)
        + ". A previsão da hora já dá o mesmo peso às semanas recentes e à média longa. "
        "Se a deriva continuar, o reforço do pico deixa de ser exceção e vira escala permanente."
    )


def _why_region(snap: dict) -> list[str]:
    lines = [
        f"Média longa desta hora e deste dia da semana: {fmt_num(snap['mean'])} ocorrência(s) por hora "
        f"({snap['samples']} amostras).",
    ]
    if snap["mean"] and abs(snap["recent"] - snap["mean"]) / max(snap["mean"], 0.05) >= 0.12:
        lines.append(
            f"As últimas quatro semanas desse recorte estão em {fmt_num(snap['recent'])}. "
            f"A previsão usa a média combinada de {fmt_num(snap['blended'])}."
        )
    else:
        lines.append(f"A média recente confirma a longa. A conta usa {fmt_num(snap['blended'])}.")
    if snap["equip_factor"] > 1.02:
        names = ", ".join(snap["sensor_names"]) or "sensores da região"
        lines.append(
            f"Sensores indisponíveis ({snap['sensors_down']} de {snap['sensors_total']}: {names}) "
            f"elevam a estimativa em {round((snap['equip_factor'] - 1) * 100)}%."
        )
    else:
        lines.append("Os sensores instalados na região não acrescentam pressão extra neste cálculo.")
    if snap["need"] == 0:
        lines.append("A demanda prevista é baixa. A escala não pede reforço.")
    elif snap["gap"] > 0:
        lines.append(
            f"A escala considerada tem {snap['have']} agente(s) e a conta pede {snap['need']} "
            f"(cada agente absorve cerca de {fmt_num(CAPACITY)} ocorrência por hora)."
        )
    else:
        lines.append(f"A escala considerada cobre a hora: {snap['have']} agente(s) para uma necessidade de {snap['need']}.")
    return lines


def _donor(data: dict, target: str, moment: datetime, mode: str) -> str | None:
    best = None
    for region in REGIONS:
        if region == target:
            continue
        snap = region_hour(data, region, moment, mode)
        spare = snap["have"] - snap["need"]
        if spare >= 1 and snap["ipo"] < 40:
            if best is None or spare > best[0] or (spare == best[0] and snap["ipo"] < best[1]):
                best = (spare, snap["ipo"], region)
    if not best:
        return None
    return best[2]


def _recommendations(data: dict, focus_day: date, real_now: datetime, found_anomalies: list[dict]) -> list[dict[str, Any]]:
    recs = []
    peaks = []
    for region in REGIONS:
        qualified = []
        for hour in range(24):
            moment = datetime(focus_day.year, focus_day.month, focus_day.day, hour, tzinfo=TZ)
            mode = _mode_for(moment, real_now)
            snap = region_hour(data, region, moment, mode)
            if snap["gap"] >= 1 and snap["ipo"] >= 58:
                qualified.append(snap)
        if not qualified:
            continue
        peaks.append(max(qualified, key=lambda snap: (snap["ipo"], snap["hour"] in (16, 17, 18, 19), snap["gap"])))
    peaks.sort(key=lambda item: (item["gap"], item["ipo"]), reverse=True)

    for snap in peaks[:3]:
        when = datetime(focus_day.year, focus_day.month, focus_day.day, snap["hour"], tzinfo=TZ)
        mode = _mode_for(when, real_now)
        donor = _donor(data, snap["region"], when, mode)
        if donor:
            action = (
                f"Deslocar {snap['gap']} agente(s) de {donor} para {snap['region']} "
                f"antes das {snap['hour']}h. {donor} fica com folga nesse horário."
            )
        else:
            action = (
                f"Posicionar {snap['gap']} agente(s) em {snap['region']} antes das {snap['hour']}h. "
                "Não há folga clara em outra região nesse turno: o reforço pede hora extra ou troca de escala."
            )
        priority = "alta" if snap["ipo"] >= 70 or snap["gap"] >= 2 else "media"
        recs.append({
            "id": f"esc-{snap['region']}-{snap['hour']}",
            "scope": "dia",
            "priority": priority,
            "title": f"Escalar {snap['gap']} agente(s) para {snap['region']} antes das {snap['hour']}h",
            "detail": (
                f"No dia projetado, o pico de {snap['region']} fica às {snap['hour']}h, "
                f"com IPO {snap['ipo']} ({snap['level_label']}). "
                f"A pressão estimada é de {fmt_num(snap['adjusted'])} ocorrência(s) por hora."
            ),
            "why": _why_region(snap),
            "action": action,
            "region": snap["region"],
            "hour": snap["hour"],
            "ipo": snap["ipo"],
        })

    broken = [
        eq for eq in data["equipment"]
        if eq["status"] in ("mau_funcionamento", "furtado") or maintenance_flag(eq, real_now.date()) == "imediata"
    ]
    if broken:
        names = ", ".join(f"{eq['serial']} ({eq['region']})" for eq in broken[:4])
        radar = next((eq for eq in broken if eq["serial"] == "RAD-SAMPAIO"), None)
        extra = ""
        if radar:
            extra = " O radar da Sampaio Vidal, em particular, zera a fiscalização de velocidade no corredor enquanto estiver fora."
        recs.append({
            "id": "manutencao-agora",
            "scope": "agora",
            "priority": "alta",
            "title": "Tirar da rua o que já está quebrado ou cego",
            "detail": f"Isto vale para qualquer dia projetado, porque já é presente: {names}.{extra}",
            "why": [
                "O IPO do dia projetado sobe enquanto estes sensores seguirem indisponíveis.",
                "Marcar o equipamento como operacional, quando ele de fato voltar, recalcula a pressão na hora.",
            ],
            "action": "Despachar manutenção primeiro para o radar da Sampaio Vidal e para a balança do KM 12. A câmera furtada pede boletim e reposição, não uma visita técnica.",
            "region": broken[0]["region"],
        })

    for item in found_anomalies[:1]:
        recs.append({
            "id": f"an-{item['region']}",
            "scope": "agora",
            "priority": "alta",
            "title": f"Ver o que está acontecendo em {item['region']} antes de só deslocar gente",
            "detail": item["detail"],
            "why": [
                "Anomalia compara o ritmo das últimas 3 horas com a média e o desvio da mesma hora no histórico.",
                "Os eventos médios do corredor não viram um alarme cada. O alarme é o conjunto.",
            ],
            "action": "Olhe câmera e radar da região, fale com a equipe local e só então dê ciência nos eventos. Ciência limpa o mapa; não abre a avenida.",
            "region": item["region"],
        })

    for series in _utilization_view(data):
        if series["id"] != "util-pat" or series["delta_pct"] is None or series["delta_pct"] > -12:
            continue
        recs.append({
            "id": "patinetes",
            "scope": "agora",
            "priority": "media",
            "title": "Investigar a queda dos patinetes da UNESP antes que o ponto esvazie",
            "detail": series["note"],
            "why": [
                f"A série de {series['unit']} cai {fmt_num(abs(series['delta_pct']))}% da primeira para a segunda metade da quinzena.",
                "O cadastro ainda diz operacional. Por isso isto é prevenção, não chamado de pane.",
            ],
            "action": "Peça ao operador a carga média e a redistribuição da frota desta semana. Se a carga estiver boa, o problema é demanda, não equipamento.",
            "region": "Campus",
        })
    return recs


def _grid(data: dict, focus_day: date, real_now: datetime) -> list[dict[str, Any]]:
    rows = []
    for region in REGIONS:
        hours = []
        for hour in range(24):
            moment = datetime(focus_day.year, focus_day.month, focus_day.day, hour, tzinfo=TZ)
            snap = region_hour(data, region, moment, _mode_for(moment, real_now))
            hours.append({
                "hour": hour,
                "ipo": snap["ipo"],
                "level": snap["level"],
                "level_label": snap["level_label"],
                "blended": snap["blended"],
                "adjusted": snap["adjusted"],
                "have": snap["have"],
                "need": snap["need"],
                "gap": snap["gap"],
                "equip_factor": snap["equip_factor"],
                "sensors_down": snap["sensors_down"],
                "mean": snap["mean"],
                "recent": snap["recent"],
            })
        peak = max(hours, key=lambda item: (item["ipo"], item["gap"]))
        rows.append({
            "region": region,
            "city": REGIONS[region]["city"],
            "lat": REGIONS[region]["lat"],
            "lng": REGIONS[region]["lng"],
            "hours": hours,
            "peak_hour": peak["hour"],
            "peak_ipo": peak["ipo"],
            "peak_level": peak["level"],
            "peak_gap": peak["gap"],
        })
    return rows


def _groups(rows: list[dict]) -> dict[str, list[str]]:
    watch, mid, calm = [], [], []
    for row in rows:
        if row["peak_ipo"] >= 58:
            watch.append(row["region"])
        elif row["peak_ipo"] >= 40:
            mid.append(row["region"])
        else:
            calm.append(row["region"])
    return {"atencao": watch, "observar": mid, "equilibrio": calm}


def _framing(today: date, focus: date) -> str:
    today_weekend = today.weekday() >= 5
    focus_weekend = focus.weekday() >= 5
    if focus == today:
        return (
            "Esta grade é o próprio dia de hoje. As horas que já passaram servem de espelho; "
            "a decisão está nas que ainda vêm."
        )
    if (not today_weekend) and focus_weekend:
        return (
            "O dia projetado é fim de semana. A pressão deixa a Sampaio Vidal e o comércio de dia útil "
            "e vai para Assis: Centro e Vila Xavier, com reflexo no Alto Cafezal. A escala pensada para Marília não cobre esse desenho."
        )
    if today_weekend and not focus_weekend:
        return (
            "O dia projetado volta a ser útil. Assis arrefece e os picos retornam à Sampaio Vidal, à Fragata e ao Centro de Marília, "
            "no começo da manhã e no fim da tarde."
        )
    if focus == today + timedelta(days=1):
        return (
            "Amanhã é do mesmo tipo de dia que hoje. O pico é recorrente: a melhor resposta é de escala, "
            "com gente posicionada antes do horário, e não um deslocamento só depois que a central encher de alertas."
        )
    return (
        "Cada célula usa o histórico do mesmo dia da semana e da mesma hora. "
        "Isto descreve o padrão. O que foge do padrão está na anomalia, olhando as últimas três horas reais."
    )


def _weekday_name(day: date) -> str:
    names = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
    months = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
    return f"{names[day.weekday()]}, {day.day} de {months[day.month - 1]}"


def _next_dow(start: date, dow: int) -> date:
    for offset in range(0, 8):
        candidate = start + timedelta(days=offset)
        if candidate.weekday() == dow:
            return candidate
    return start


def _relation(today: date, focus: date) -> str:
    if focus == today:
        return "hoje"
    if focus == today + timedelta(days=1):
        return "amanhã"
    return "no dia escolhido"


def _horizon(data: dict, moment: datetime) -> list[dict[str, Any]]:
    rows = []
    for step in range(0, 6):
        instant = moment.replace(minute=0, second=0, microsecond=0) + timedelta(hours=step)
        snaps = [region_hour(data, region, instant, _mode_for(instant, moment)) for region in REGIONS]
        top = max(snaps, key=lambda item: item["ipo"])
        rows.append({
            "hour": instant.hour,
            "label": f"{instant.hour:02d}h",
            "region": top["region"],
            "ipo": top["ipo"],
            "level": top["level"],
            "level_label": top["level_label"],
            "gap": top["gap"],
        })
    return rows


def _gauss(matrix: list[list[float]], target: list[float]) -> list[float] | None:
    size = len(target)
    rows = [list(matrix[i]) + [target[i]] for i in range(size)]
    for col in range(size):
        pivot = max(range(col, size), key=lambda row: abs(rows[row][col]))
        rows[col], rows[pivot] = rows[pivot], rows[col]
        if abs(rows[col][col]) < 1e-9:
            return None
        scale = rows[col][col]
        for col2 in range(col, size + 1):
            rows[col][col2] /= scale
        for row in range(size):
            if row == col:
                continue
            factor = rows[row][col]
            for col2 in range(col, size + 1):
                rows[row][col2] -= factor * rows[col][col2]
    return [rows[i][size] for i in range(size)]


def _demand_model(data: dict, focus: date) -> dict[str, Any]:
    """Uma regressão por região, em cima dos volumes já observados."""
    weekend_focus = 1.0 if focus.weekday() >= 5 else 0.0
    rows = []
    used = 0
    for region in REGIONS:
        samples_x: list[list[float]] = []
        samples_y: list[float] = []
        for hour in range(7, 22):
            for dow in (1, 5):
                raw = data["history"]["buckets"].get(_bucket_key(region, dow, hour), [])
                if len(raw) < 4:
                    continue
                window = raw[-8:]
                samples_x.append([1.0, HOUR_SHAPE[hour], 1.0 if dow >= 5 else 0.0])
                samples_y.append(sum(window) / len(window))
        if len(samples_y) < 8:
            continue
        used += len(samples_y)
        width = 3
        xtx = [[0.0] * width for _ in range(width)]
        xty = [0.0] * width
        for features, target in zip(samples_x, samples_y):
            for i in range(width):
                xty[i] += features[i] * target
                for j in range(width):
                    xtx[i][j] += features[i] * features[j]
        beta = _gauss(xtx, xty)
        if beta is None:
            continue
        mean = sum(samples_y) / len(samples_y)
        total = sum((value - mean) ** 2 for value in samples_y) or 1.0
        residual = 0.0
        for features, target in zip(samples_x, samples_y):
            predicted = sum(weight * value for weight, value in zip(beta, features))
            residual += (target - predicted) ** 2
        confidence = int(round(max(0, min(0.99, 1 - residual / total)) * 100))
        features = [1.0, HOUR_SHAPE[18], weekend_focus]
        predicted = max(0.0, sum(weight * value for weight, value in zip(beta, features)))
        rows.append({
            "region": region,
            "hour": "18h",
            "predicted": round(predicted, 2),
            "confidence": confidence,
        })
    if not rows:
        return {"name": "Regressão linear", "confidence": 0, "note": "Amostra insuficiente para treinar.", "rows": []}
    rows.sort(key=lambda item: -item["predicted"])
    top = rows[0]
    day = "no fim de semana" if weekend_focus else "em dia útil"
    return {
        "name": "Regressão linear por região",
        "confidence": top["confidence"],
        "features": "formato da hora e fim de semana, ajustados no histórico de cada região",
        "samples": used,
        "note": (
            f"O que foi previsto: {top['region']} às 18h {day}, volume {top['predicted']}. "
            f"Por que: o ajuste usa os volumes já registrados dessa região nesse tipo de dia, não a equipe que está na rua. "
            f"Confiança do modelo: {top['confidence']}%. "
            "Ação: reposicionar uma equipe para essa região antes das 18h se a escala local estiver curta."
        ),
        "rows": rows[:4],
    }


def predictions(data: dict, moment: datetime | None = None, focus: date | None = None) -> dict[str, Any]:
    moment = moment or now_local()
    today = moment.date()
    focus = focus or (today + timedelta(days=1))
    found = anomalies(data, moment)
    grid = _grid(data, focus, moment)
    daily = data["history"]["daily"]
    return {
        "generated_at": iso(moment),
        "today": today.isoformat(),
        "focus_date": focus.isoformat(),
        "focus_label": _weekday_name(focus),
        "relation": _relation(today, focus),
        "framing": _framing(today, focus),
        "method": METHOD,
        "grid": grid,
        "groups": _groups(grid),
        "recommendations": _recommendations(data, focus, moment, found),
        "horizon_6h": _horizon(data, moment),
        "anomalies": found,
        "equipment_risks": equipment_risks(data, today),
        "live_regions": [region_hour(data, region, moment, "live") for region in REGIONS],
        "trends": {
            "incidents": {
                "points": [{"date": day["date"], "count": day["count"]} for day in daily],
                "note": _incident_trend_note(daily),
            },
            "availability": _availability_view(data, today),
            "utilization": _utilization_view(data),
        },
        "shortcuts": {
            "today": today.isoformat(),
            "tomorrow": (today + timedelta(days=1)).isoformat(),
            "saturday": _next_dow(today, 5).isoformat(),
            "weekday": _next_dow(today, 1).isoformat(),
        },
        "ml": _demand_model(data, focus),
    }


def present_equipment(eq: dict, today: date) -> dict[str, Any]:
    out = dict(eq)
    out["maintenance_flag"] = maintenance_flag(eq, today)
    out["type_label"] = TYPES[eq["type"]]["label"]
    out["history"] = list(eq.get("history") or [])[:8]
    return out


def present_agent(agent: dict) -> dict[str, Any]:
    out = dict(agent)
    duty = duty_of(agent)
    out["on_duty"] = agent["status"] in ACTIVE_AGENT or bool(agent.get("mission"))
    out["duty"] = duty
    out["duty_label"] = DUTY_LABEL[duty]
    out["mission"] = agent.get("mission")
    out["plan"] = agent.get("plan")
    out["route"] = agent.get("route")
    signal, age = _freshness(agent.get("last_seen"), now_local())
    out["signal"] = signal
    out["signal_min"] = age
    out["stale"] = bool(agent.get("signal_hold")) or (duty == "disponivel" and age >= 20)
    return out


def bootstrap(data: dict, moment: datetime | None = None) -> dict[str, Any]:
    moment = moment or now_local()
    today = moment.date()
    alerts = derive_alerts(data, moment)
    index = city_index(data, moment, alerts)
    preview = predictions(data, moment, today + timedelta(days=1))
    top = [rec for rec in preview["recommendations"] if rec["scope"] == "dia"][:2]
    board = region_board(data, index["regions"])
    return {
        "city": {
            "name": "Marília, Assis e Cândido Mota",
            "uf": "SP",
            "pilot": "F.O.G.O.",
            "note": "Ambiente de demonstração com dados sintéticos sobre Marília, Assis e Cândido Mota.",
        },
        "clock": iso(moment),
        "kpis": kpis(data),
        "city_index": {
            "value": index["value"],
            "band": index["band"],
            "label": index["label"],
            "hot_region": index["hot_region"],
            "hot_ipo": index["hot_ipo"],
            "sentence": index["sentence"],
        },
        "alerts": alerts,
        "feed": data["feed"][:20],
        "incidents": [present_incident(data, inc) for inc in data["incidents"]],
        "equipment": [present_equipment(eq, today) for eq in data["equipment"]],
        "agents": [present_agent(agent) for agent in data["agents"]],
        "regions": board,
        "health": operational_health(data, moment, index, board),
        "now": operational_now(data, board),
        "attention": attention_queue(data, moment, alerts, preview),
        "changes": recent_changes(data, moment),
        "schema": schema_public(),
        "preview": {
            "tomorrow_label": preview["focus_label"],
            "framing": preview["framing"],
            "top": top,
        },
        "vehicles": __import__("ops_vehicles").present_all(data),
        "events": list(data.get("events") or [])[:80],
        "orders": __import__("ops_orders").present_all(data, moment),
    }


def tick_payload(data: dict, moment: datetime | None = None) -> dict[str, Any]:
    snap = bootstrap(data, moment)
    moves = []
    for agent in snap["agents"]:
        if agent["status"] in ACTIVE_AGENT or agent["status"] == "em_deslocamento":
            moves.append({
                "kind": "agent", "id": agent["id"], "lat": agent["lat"], "lng": agent["lng"],
                "status": agent["status"], "duty": agent["duty"],
            })
    for eq in snap["equipment"]:
        if eq["type"] in MOVING_TYPES or eq["status"] == "operacional":
            moves.append({
                "kind": "equipment", "id": eq["id"], "lat": eq["lat"], "lng": eq["lng"],
                "last_seen": eq.get("last_seen"), "status": eq["status"],
            })
    return {
        "kind": "tick",
        "clock": snap["clock"],
        "kpis": snap["kpis"],
        "city_index": snap["city_index"],
        "alerts": snap["alerts"],
        "feed": snap["feed"],
        "incidents": snap["incidents"],
        "regions": snap["regions"],
        "health": snap["health"],
        "now": snap["now"],
        "attention": snap["attention"],
        "changes": snap["changes"],
        "preview": snap["preview"],
        "moves": moves,
    }


# ---------- validação e mutações ----------

class Invalid(Exception):
    pass


def _clean_text(value: Any, label: str, limit: int = 120, required: bool = True) -> str:
    text = "" if value is None else str(value).strip()
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    if required and not text:
        raise Invalid(f"Informe {label}.")
    if len(text) > limit:
        raise Invalid(f"{label} passa de {limit} caracteres.")
    return text


def _cep_norm(value: Any) -> str:
    digits = re.sub(r"\D", "", "" if value is None else str(value))
    if len(digits) != 8:
        raise Invalid("CEP precisa ter 8 dígitos.")
    return f"{digits[:5]}-{digits[5:]}"


def _coord(value: Any, label: str, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise Invalid(f"Informe {label} com um número.")
    if not low <= number <= high:
        raise Invalid(f"{label} está fora do intervalo permitido.")
    return round(number, 6)


def _choice(value: Any, label: str, options: list[str]) -> str:
    text = _clean_text(value, label, 80)
    if text not in options:
        raise Invalid(f"{label} não é uma opção válida.")
    return text


def _validate_attrs(typ: str, raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    clean: dict[str, Any] = {}
    for field in TYPES[typ]["fields"]:
        show = field.get("show_if")
        if show:
            key, expected = next(iter(show.items()))
            current = raw.get(key, clean.get(key))
            if current != expected:
                continue
        value = raw.get(field["key"])
        if field["type"] == "bool":
            clean[field["key"]] = bool(value)
            continue
        if value in (None, "") and field.get("optional"):
            continue
        if field["type"] == "select":
            clean[field["key"]] = _choice(value, field["label"], field["options"])
        elif field["type"] == "number":
            try:
                number = float(value)
            except (TypeError, ValueError):
                raise Invalid(f"Informe {field['label']}.")
            if not field["min"] <= number <= field["max"]:
                raise Invalid(f"{field['label']} deve ficar entre {field['min']} e {field['max']}.")
            clean[field["key"]] = int(number) if float(number).is_integer() else round(number, 1)
        else:
            clean[field["key"]] = _clean_text(value, field["label"], field.get("max", 60))
    if typ == "radar" and clean.get("radar_kind") == "Velocidade" and "speed_limit" not in clean:
        raise Invalid("Informe a velocidade máxima do radar.")
    if raw.get("paired_agent_id"):
        clean["paired_agent_id"] = str(raw["paired_agent_id"])
    return clean


def _date_or_none(value: Any, label: str) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        raise Invalid(f"{label} precisa estar no formato AAAA-MM-DD.")


def _location_fields(payload: dict[str, Any]) -> dict[str, Any]:
    region = _choice(payload.get("region"), "a região", list(REGIONS))
    return {
        "region": region,
        "neighborhood": _clean_text(payload.get("neighborhood"), "o bairro", 80),
        "city": _clean_text(payload.get("city"), "a cidade", 80),
        "uf": _clean_text(payload.get("uf"), "a UF", 2).upper(),
        "cep": _cep_norm(payload.get("cep")),
        "street": _clean_text(payload.get("street"), "a rua", 120),
        "reference": _clean_text(payload.get("reference"), "a referência", 120),
        "lat": _coord(payload.get("lat"), "a latitude", -34, 6),
        "lng": _coord(payload.get("lng"), "a longitude", -74, -32),
    }


def _check_unique(items: list[dict], field: str, value: str, ignore: str | None, label: str) -> None:
    for item in items:
        if item["id"] == ignore:
            continue
        if str(item.get(field, "")).lower() == value.lower():
            raise Invalid(f"Já existe um registro com {label} {value}.")


def clean_equipment(data: dict, payload: dict[str, Any], ignore: str | None = None) -> dict[str, Any]:
    typ = _choice(payload.get("type"), "o tipo", list(TYPES))
    status = _choice(payload.get("status"), "a situação", [key for key, _ in EQUIPMENT_STATUSES])
    need = _choice(payload.get("maintenance_need"), "a necessidade de manutenção", [key for key, _ in MAINTENANCE_NEEDS])
    nxt = _date_or_none(payload.get("next_maintenance"), "A data da próxima manutenção")
    if need == "agendada" and not nxt:
        raise Invalid("Informe a data da próxima manutenção.")
    if status == "ainda_nao_instalado":
        installed = None
    else:
        installed = _date_or_none(payload.get("installed_at"), "A data de instalação")
    serial = _clean_text(payload.get("serial"), "o número de série", 40).upper()
    _check_unique(data["equipment"], "serial", serial, ignore, "série")
    clean = {
        "type": typ,
        "serial": serial,
        "brand": _clean_text(payload.get("brand"), "a marca", 60),
        "model": _clean_text(payload.get("model"), "o modelo", 60),
        "agency": _choice(payload.get("agency"), "o órgão", AGENCIES),
        "status": status,
        "maintenance_need": need,
        "next_maintenance": nxt,
        "installed_at": installed,
        "notes": _clean_text(payload.get("notes"), "as observações", 500, required=False),
        "attrs": _validate_attrs(typ, payload.get("attrs") or {}),
        **_location_fields(payload),
    }
    if len(clean["uf"]) != 2:
        raise Invalid("UF precisa ter 2 letras.")
    return clean


def clean_agent(data: dict, payload: dict[str, Any], ignore: str | None = None) -> dict[str, Any]:
    registration = _clean_text(payload.get("registration"), "a matrícula", 20).upper()
    _check_unique(data["agents"], "registration", registration, ignore, "matrícula")
    clean = {
        "name": _clean_text(payload.get("name"), "o nome", 80),
        "registration": registration,
        "agency": _choice(payload.get("agency"), "o órgão", ["Secretaria de Mobilidade", "Guarda Municipal", "Polícia Militar"]),
        "role": _clean_text(payload.get("role"), "a função", 60),
        "shift": _choice(payload.get("shift"), "o turno", SHIFTS),
        "status": _choice(payload.get("status"), "a situação", [key for key, _ in AGENT_STATUSES]),
        "phone": _clean_text(payload.get("phone"), "o telefone", 20, required=False),
        "team": _clean_text(payload.get("team"), "a equipe", 60, required=False),
        "notes": _clean_text(payload.get("notes"), "as observações", 500, required=False),
        **_location_fields(payload),
    }
    if len(clean["uf"]) != 2:
        raise Invalid("UF precisa ter 2 letras.")
    return clean


def create_equipment(data: dict, payload: dict[str, Any], moment: datetime) -> dict:
    clean = clean_equipment(data, payload)
    eq = {
        "id": _next_id(data, "equipment", "EQ"),
        **clean,
        "last_seen": iso(moment) if clean["status"] == "operacional" else None,
        "history": [{"at": iso(moment), "text": "Equipamento cadastrado."}],
        "created_at": iso(moment),
        "updated_at": iso(moment),
    }
    data["equipment"].append(eq)
    push_feed(data, "info", f"{eq['serial']} entrou no inventário em {eq['neighborhood']}.", eq["region"], moment)
    return eq


def update_equipment(data: dict, eid: str, payload: dict[str, Any], moment: datetime) -> dict:
    eq = _must(data["equipment"], eid, "Equipamento")
    clean = clean_equipment(data, payload, ignore=eid)
    previous = eq["status"]
    eq.update(clean)
    eq["updated_at"] = iso(moment)
    if clean["status"] == "operacional":
        eq["last_seen"] = iso(moment)
    eq.setdefault("history", [])
    if previous != clean["status"]:
        label = dict(EQUIPMENT_STATUSES).get(clean["status"], clean["status"])
        eq["history"].insert(0, {"at": iso(moment), "text": f"Situação alterada para {label}."})
        del eq["history"][12:]
        push_feed(
            data, "atencao" if clean["status"] in BAD_STATUS else "info",
            f"{eq['serial']} passou de {previous} para {clean['status']}.",
            eq["region"], moment,
        )
    __import__("ops_orders").reconcile(data, moment)
    return eq


def patch_equipment(data: dict, eid: str, payload: dict[str, Any], moment: datetime) -> dict:
    eq = _must(data["equipment"], eid, "Equipamento")
    merged = {**eq, "attrs": eq.get("attrs") or {}}
    for key in ("status", "maintenance_need", "next_maintenance", "notes", "lat", "lng"):
        if key in payload:
            merged[key] = payload[key]
    return update_equipment(data, eid, merged, moment)


def delete_equipment(data: dict, eid: str, moment: datetime) -> None:
    eq = _must(data["equipment"], eid, "Equipamento")
    data["equipment"] = [item for item in data["equipment"] if item["id"] != eid]
    for agent in data["agents"]:
        if agent.get("paired_equipment_id") == eid:
            agent["paired_equipment_id"] = None
    push_feed(data, "info", f"{eq['serial']} foi removido do inventário.", eq["region"], moment)


def create_agent(data: dict, payload: dict[str, Any], moment: datetime) -> dict:
    clean = clean_agent(data, payload)
    agent = {
        "id": _next_id(data, "agent", "AG"),
        **clean,
        "base_region": clean["region"],
        "base_lat": clean["lat"],
        "base_lng": clean["lng"],
        "paired_equipment_id": None,
        "last_seen": iso(moment),
        "created_at": iso(moment),
        "updated_at": iso(moment),
    }
    data["agents"].append(agent)
    push_feed(data, "info", f"{agent['name']} ({agent['registration']}) entrou na escala de {agent['region']}.", agent["region"], moment)
    return agent


def update_agent(data: dict, aid: str, payload: dict[str, Any], moment: datetime) -> dict:
    agent = _must(data["agents"], aid, "Agente")
    clean = clean_agent(data, payload, ignore=aid)
    agent.update(clean)
    agent["base_region"] = clean["region"]
    agent["base_lat"] = clean["lat"]
    agent["base_lng"] = clean["lng"]
    agent["updated_at"] = iso(moment)
    agent["last_seen"] = iso(moment)
    return agent


def delete_agent(data: dict, aid: str, moment: datetime) -> None:
    agent = _must(data["agents"], aid, "Agente")
    data["agents"] = [item for item in data["agents"] if item["id"] != aid]
    for eq in data["equipment"]:
        if eq.get("attrs", {}).get("paired_agent_id") == aid:
            eq["attrs"].pop("paired_agent_id", None)
    push_feed(data, "info", f"{agent['name']} saiu da escala.", agent["region"], moment)


def acknowledge(data: dict, incident_id: str, moment: datetime) -> dict:
    incident = _must(data["incidents"], incident_id, "Ocorrência")
    incident["status"] = "encerrada"
    incident["acked_at"] = iso(moment)
    _log_incident(incident, "Central registrou ciência e encerrou sem nova equipe.", moment)
    _release_agent(data, incident.get("assigned_agent_id"), moment, keep_feed=False)
    incident["assigned_agent_id"] = None
    incident.pop("route", None)
    push_feed(data, "info", f"Ocorrência {incident_number(incident)} encerrada com ciência da central.", incident["region"], moment)
    return incident


def _must(items: list[dict], item_id: str, label: str) -> dict:
    for item in items:
        if item["id"] == item_id:
            return item
    raise Invalid(f"{label} não encontrado.")


def apply_scenario(data: dict, name: str, moment: datetime) -> dict[str, Any]:
    if name == "acidente":
        incident = {
            "id": _next_id(data, "incident", "OC"),
            "kind": "sinistro",
            "severity": "alta",
            "status": "aberto",
            "analytical": True,
            "title": "Sinistro com uma faixa bloqueada no Centro",
            "detail": "Colisão no entorno da Rua São Luiz. A via segue parcialmente fechada.",
            "region": "Centro Marília",
            "street": "Rua São Luiz",
            "reference": "número 181",
            "lat": -22.2146,
            "lng": -49.9460,
            "at": iso(moment),
        }
        data["incidents"].insert(0, incident)
        push_feed(data, "critico", incident["title"] + ".", "Centro Marília", moment)
        return {"message": "Sinistro lançado no Centro de Marília. O alerta crítico subiu na fila.", "focus": {"kind": "incident", "id": incident["id"]}}

    if name == "falha-radar":
        radar = next((eq for eq in data["equipment"] if eq["type"] == "radar" and eq["status"] == "operacional"), None)
        if radar is None:
            raise Invalid("Não há radar operacional para este exercício. Restaure a demonstração.")
        radar["status"] = "mau_funcionamento"
        radar["maintenance_need"] = "imediata"
        radar["next_maintenance"] = moment.date().isoformat()
        radar["updated_at"] = iso(moment)
        radar["last_seen"] = iso(moment - timedelta(minutes=8))
        push_feed(data, "critico", f"{radar['serial']} entrou em mau funcionamento em {radar['neighborhood']}.", radar["region"], moment)
        return {"message": f"{radar['serial']} saiu do ar. A pressão da região sobe enquanto ele seguir fora.", "focus": {"kind": "equipment", "id": radar["id"]}}

    if name == "furto":
        camera = next((eq for eq in data["equipment"] if eq["type"] == "camera" and eq["status"] == "operacional"), None)
        if camera is None:
            raise Invalid("Não há câmera operacional para este exercício. Restaure a demonstração.")
        camera["status"] = "furtado"
        camera["maintenance_need"] = "nenhuma"
        camera["updated_at"] = iso(moment)
        push_feed(data, "critico", f"{camera['serial']} foi marcada como furtada em {camera['street']}.", camera["region"], moment)
        return {"message": f"{camera['serial']} ficou cega. O ponto sai do mapa como recurso e entra como perda.", "focus": {"kind": "equipment", "id": camera["id"]}}

    if name == "surto":
        region = "Centro Assis"
        mean, std, _, _, _ = bucket_stats(data, region, moment.weekday(), moment.hour)
        target = min(6, max(4, math.ceil(max(0.9, mean * 2) * ANOMALY_WINDOW_H)))
        for i in range(target):
            lat, lng = _jitter(random.Random(SEED + 50 + i), REGIONS[region]["lat"], REGIONS[region]["lng"], 350)
            incident = {
                "id": _next_id(data, "incident", "OC"),
                "kind": "aglomeracao",
                "severity": "media",
                "status": "aberto",
                "analytical": True,
                "title": "Aglomeração e estacionamento irregular no centro de Assis",
                "detail": "Evento analítico do exercício. O conjunto é que deve disparar a anomalia.",
                "region": region,
                "lat": lat,
                "lng": lng,
                "at": iso(moment - timedelta(minutes=5 + i * 8)),
            }
            data["incidents"].insert(0, incident)
        push_feed(data, "critico", "Surto de ocorrências registrado no centro de Assis.", region, moment)
        return {"message": "Surto lançado em Assis. Se o ritmo passar da média da hora, a anomalia acende.", "focus": {"kind": "region", "id": region}}

    if name == "silencio":
        camera = next((eq for eq in data["equipment"] if eq["type"] == "camera" and eq["status"] == "operacional"), None)
        if camera is None:
            raise Invalid("Não há câmera operacional para silenciar.")
        camera["last_seen"] = iso(moment - timedelta(minutes=12))
        camera["updated_at"] = iso(moment)
        push_feed(data, "atencao", f"{camera['serial']} parou de falar há 12 minutos e segue como operacional.", camera["region"], moment)
        return {
            "message": f"{camera['serial']} ficou em silêncio de telemetria. O status não mudou: o sintoma é a ausência de sinal.",
            "focus": {"kind": "equipment", "id": camera["id"]},
        }

    if name == "chuva":
        region = "Sampaio Vidal"
        mean, _, _, _, _ = bucket_stats(data, region, moment.weekday(), moment.hour)
        projected = min(100, round(100 * (mean * 1.25) / 2.35))
        push_feed(data, "atencao", f"Exercício de chuva forte em {region}. Cadastro não foi alterado.", region, moment)
        return {
            "message": (
                f"Exercício de chuva em {region}. A média desta hora, com fator 1,25, "
                f"apontaria pressão perto de {projected}. Nenhum equipamento mudou de situação. "
                "O fator segue a leitura de que chuva aumenta ocorrência; o Open-Meteo entra só quando a consulta de clima responde."
            ),
            "focus": {"kind": "region", "id": region},
        }

    raise Invalid("Cenário desconhecido.")


def simulate_tick(data: dict, rng: random.Random, moment: datetime) -> None:
    data["meta"]["tick"] = data["meta"].get("tick", 0) + 1
    by_id = {eq["id"]: eq for eq in data["equipment"]}
    for eq in data["equipment"]:
        if eq["status"] == "operacional" and eq["type"] in SENSOR_TYPES:
            eq["last_seen"] = iso(moment)
        if not _should_move(eq, by_id, data):
            continue
        home_lat = eq.get("lat")
        home_lng = eq.get("lng")
        paired = eq.get("attrs", {}).get("paired_agent_id")
        if paired:
            agent = next((a for a in data["agents"] if a["id"] == paired), None)
            if agent and agent.get("mission"):
                continue
            if agent:
                home_lat, home_lng = agent["base_lat"], agent["base_lng"]
        _nudge(eq, rng, home_lat, home_lng, REGIONS.get(eq["region"], {}).get("radius", 700))
        eq["last_seen"] = iso(moment)

    for agent in data["agents"]:
        mission = agent.get("mission") or {}
        phase = mission.get("phase")
        paired = by_id.get(agent.get("paired_equipment_id") or "")
        if phase:
            incident = next((item for item in data["incidents"] if item["id"] == mission.get("incident_id")), None)
            if incident and phase == "deslocamento":
                _step_towards(agent, incident["lat"], incident["lng"], 90)
            elif incident:
                agent["lat"], agent["lng"] = incident["lat"], incident["lng"]
            if paired:
                paired["lat"], paired["lng"] = agent["lat"], agent["lng"]
                paired["last_seen"] = iso(moment)
            if not agent.get("signal_hold"):
                agent["last_seen"] = iso(moment)
            continue
        if agent["status"] not in ACTIVE_AGENT:
            continue
        if paired and _should_move(paired, by_id, data):
            agent["lat"], agent["lng"] = paired["lat"], paired["lng"]
        else:
            _nudge(agent, rng, agent["base_lat"], agent["base_lng"], 650)
        if not agent.get("signal_hold"):
            agent["last_seen"] = iso(moment)

    if data["meta"]["tick"] % 20 == 0:
        data.setdefault("replay", []).append(capture_frame(data, moment))
        del data["replay"][:-36]

    if data["meta"]["tick"] % 8 == 0:
        _ambient(data, rng, moment)
    __import__("ops_vehicles").follow(data)


def _should_move(eq: dict, by_id: dict, data: dict) -> bool:
    if eq["type"] not in MOVING_TYPES or eq["status"] != "operacional":
        return False
    if eq["type"] == "transporte" and not eq.get("attrs", {}).get("in_service", True):
        return False
    paired = eq.get("attrs", {}).get("paired_agent_id")
    if paired:
        agent = next((a for a in data["agents"] if a["id"] == paired), None)
        if agent and agent["status"] not in ACTIVE_AGENT:
            return False
    return True


def _step_towards(item: dict, lat: float, lng: float, meters: float) -> None:
    dist = _haversine(item["lat"], item["lng"], lat, lng)
    if dist <= meters:
        item["lat"], item["lng"] = round(lat, 6), round(lng, 6)
        return
    frac = meters / dist
    item["lat"] = round(item["lat"] + (lat - item["lat"]) * frac, 6)
    item["lng"] = round(item["lng"] + (lng - item["lng"]) * frac, 6)


def _nudge(item: dict, rng: random.Random, home_lat: float, home_lng: float, radius: float) -> None:
    lat = item["lat"] + (rng.random() - 0.5) * 0.0014
    lng = item["lng"] + (rng.random() - 0.5) * 0.0014
    if _haversine(lat, lng, home_lat, home_lng) > radius:
        lat = lat + (home_lat - lat) * 0.45
        lng = lng + (home_lng - lng) * 0.45
    item["lat"] = round(lat, 6)
    item["lng"] = round(lng, 6)


def _ambient(data: dict, rng: random.Random, moment: datetime) -> None:
    pool = [eq for eq in data["equipment"] if eq["status"] == "operacional"]
    if not pool:
        return
    eq = rng.choice(pool)
    if eq["type"] == "radar":
        text = f"{eq['serial']} registrou fluxo dentro do limite em {eq['street']}."
    elif eq["type"] == "camera":
        text = f"{eq['serial']} transmite normalmente em {eq['neighborhood']}."
    elif eq["type"] == "patinete":
        text = f"Ponto {eq['serial']} reportou {eq['attrs'].get('fleet_size', 0)} patinetes disponíveis."
    elif eq["type"] in MOVING_TYPES:
        text = f"{eq['serial']} segue em deslocamento por {eq['region']}."
    else:
        text = f"{eq['serial']} enviou telemetria ordinária."
    push_feed(data, "info", text, eq["region"], moment)


OPEN_INCIDENT = {"aberto", "em_deslocamento", "no_local", "em_atendimento"}
DUTY_LABEL = {
    "disponivel": "Disponível",
    "em_atendimento": "Em atendimento",
    "em_deslocamento": "Em deslocamento",
    "indisponivel": "Indisponível",
}
PRIORITY_LABEL = {
    "critica": "Crítica",
    "alta": "Alta",
    "media": "Média",
    "baixa": "Baixa",
}
INCIDENT_STATUS_LABEL = {
    "aberto": "Aguardando equipe",
    "em_deslocamento": "Equipe a caminho",
    "no_local": "No local",
    "em_atendimento": "Em atendimento",
    "encerrada": "Encerrada",
    "ciencia": "Encerrada",
}
KIND_LABEL = {
    "sinistro": "Sinistro",
    "congestionamento": "Congestionamento",
    "aglomeracao": "Aglomeração",
    "estacionamento": "Estacionamento",
}


def duty_of(agent: dict) -> str:
    mission = agent.get("mission") or {}
    if mission:
        return "em_deslocamento" if mission.get("phase") == "deslocamento" else "em_atendimento"
    if agent.get("status") in ("fora_de_servico", "em_pausa"):
        return "indisponivel"
    if agent.get("status") == "em_deslocamento":
        return "em_deslocamento"
    if agent.get("status") == "em_atividade":
        return "disponivel"
    return "indisponivel"


def priority_of(incident: dict) -> str:
    value = incident.get("priority")
    if value in PRIORITY_LABEL:
        return value
    return {"alta": "alta", "media": "media", "baixa": "baixa"}.get(incident.get("severity"), "media")


def incident_number(incident: dict) -> str:
    digits = "".join(char for char in incident["id"] if char.isdigit())
    return digits[-4:].zfill(4)


def _log_incident(incident: dict, text: str, moment: datetime) -> None:
    incident.setdefault("timeline", []).append({"at": iso(moment), "text": text})


def _release_agent(data: dict, agent_id: str | None, moment: datetime, keep_feed: bool = True) -> None:
    if not agent_id:
        return
    agent = next((item for item in data["agents"] if item["id"] == agent_id), None)
    if not agent:
        return
    agent["mission"] = None
    agent["route"] = None
    if agent["status"] != "fora_de_servico":
        agent["status"] = "em_atividade"
    agent["updated_at"] = iso(moment)
    agent["last_seen"] = iso(moment)
    if keep_feed:
        push_feed(data, "info", f"{agent['name']} voltou a disponível.", agent["region"], moment)


def _km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    return _haversine(lat1, lng1, lat2, lng2) / 1000


def _eta(km: float) -> int:
    return max(2, round(km / 28 * 60))


def _freshness(moment_iso: str | None, now: datetime) -> tuple[str, int]:
    if not moment_iso:
        return "sem comunicação", 999
    minutes = int((now - parse_iso(moment_iso)).total_seconds() // 60)
    if minutes <= 2:
        return "atualizado", minutes
    if minutes <= 15:
        return "atrasado", minutes
    return "sem comunicação", minutes


def _specialty_fit(agent: dict, incident: dict) -> tuple[int, str]:
    kind = incident.get("kind")
    role = agent.get("role") or ""
    if kind in ("sinistro", "congestionamento", "estacionamento") and "trânsito" in role.lower():
        return 18, "especialização compatível com trânsito"
    if kind == "aglomeracao" and "Guarda" in role:
        return 16, "especialização compatível com segurança local"
    if kind == "sinistro" and agent.get("agency") == "Polícia Militar":
        return 10, "pode apoiar sinistro"
    return 0, ""


def _coverage_pct(free_count: int) -> int:
    return min(100, free_count * 40)


def nearest_agents(data: dict, incident: dict, limit: int = 4) -> list[dict[str, Any]]:
    now = now_local()
    rows = []
    free_by_region: dict[str, int] = {}
    for agent in data["agents"]:
        if duty_of(agent) == "disponivel":
            free_by_region[agent["region"]] = free_by_region.get(agent["region"], 0) + 1
    for agent in data["agents"]:
        if agent.get("status") in ("fora_de_servico", "em_pausa") or agent.get("mission"):
            continue
        km = _km(agent["lat"], agent["lng"], incident["lat"], incident["lng"])
        eta = _eta(km)
        duty = duty_of(agent)
        signal, age = _freshness(agent.get("last_seen"), now)
        stale = bool(agent.get("signal_hold")) or (duty == "disponivel" and age >= 20)
        bonus, specialty = _specialty_fit(agent, incident)
        origin_free = free_by_region.get(agent["region"], 0)
        leaves_origin_empty = agent["region"] != incident.get("region") and origin_free <= 1
        score = 100 - min(80, eta) + bonus
        if stale:
            score -= 40
        if duty == "em_deslocamento":
            score -= 8
        if leaves_origin_empty:
            score -= 22
        reasons = []
        if eta <= 8:
            reasons.append("proximidade")
        elif eta >= 40:
            reasons.append(f"distância de {eta} min")
        else:
            reasons.append(f"ETA de {eta} min")
        if specialty:
            reasons.append(specialty)
        if stale:
            reasons.append("sinal sem confirmação")
        elif duty == "disponivel":
            reasons.append("disponibilidade")
        if leaves_origin_empty:
            reasons.append(f"esvaziamento de {agent['region']}")
        before = _coverage_pct(origin_free)
        after = _coverage_pct(max(0, origin_free - 1))
        if leaves_origin_empty:
            impact = (
                f"{incident.get('region')} recebe atendimento em cerca de {eta} min. "
                f"{agent['region']} fica sem equipe livre por cerca de {max(eta, 10)} min. "
                f"Cobertura da origem cai de {before}% para {after}%."
            )
        else:
            impact = (
                f"{incident.get('region')} recebe atendimento em cerca de {eta} min. "
                f"{agent['region']} segue com {max(0, origin_free - 1)} equipe(s) livre(s). "
                f"Cobertura da origem vai de {before}% para {after}%."
            )
        rows.append({
            "id": agent["id"],
            "name": agent["name"],
            "team": agent.get("team") or "Equipe de campo",
            "registration": agent["registration"],
            "region": agent["region"],
            "role": agent.get("role") or "",
            "duty": duty,
            "duty_label": DUTY_LABEL[duty],
            "km": round(km, 1),
            "eta_min": eta,
            "signal": signal,
            "signal_min": age,
            "stale": stale,
            "score": score,
            "specialty": specialty or "sem especialização específica",
            "load": "em deslocamento" if duty == "em_deslocamento" else "sem missão",
            "recommended": False,
            "reason": "Motivos: " + ", ".join(reasons) + ".",
            "impact": impact,
            "coverage_before": before,
            "coverage_after": after,
        })
    rows.sort(key=lambda item: (-item["score"], item["km"], item["name"]))
    if rows and not rows[0]["stale"]:
        rows[0]["recommended"] = True
        rows[0]["reason"] = "Recomendada por " + rows[0]["reason"].removeprefix("Motivos: ")
    picked = rows[:3]
    if len(rows) > 3:
        far = max(rows, key=lambda item: item["eta_min"])
        if far not in picked:
            picked.append(far)
    return picked


def present_incident(data: dict, incident: dict) -> dict[str, Any]:
    priority = priority_of(incident)
    assigned = next((agent for agent in data["agents"] if agent["id"] == incident.get("assigned_agent_id")), None)
    status = incident.get("status") or "aberto"
    out = {
        "id": incident["id"],
        "number": incident_number(incident),
        "kind": incident.get("kind") or "ocorrencia",
        "kind_label": KIND_LABEL.get(incident.get("kind"), "Ocorrência"),
        "severity": incident.get("severity") or "media",
        "priority": priority,
        "priority_label": PRIORITY_LABEL[priority],
        "status": status,
        "status_label": INCIDENT_STATUS_LABEL.get(status, status),
        "title": incident.get("title") or "Ocorrência",
        "detail": incident.get("detail") or "",
        "region": incident.get("region"),
        "street": incident.get("street") or "Ponto informado à central",
        "reference": incident.get("reference") or incident.get("region"),
        "lat": incident.get("lat"),
        "lng": incident.get("lng"),
        "at": incident.get("at"),
        "assigned_agent_id": incident.get("assigned_agent_id"),
        "assigned_name": assigned["name"] if assigned else None,
        "assigned_team": assigned.get("team") if assigned else None,
        "timeline": list(incident.get("timeline") or [{"at": incident.get("at"), "text": "Ocorrência registrada."}]),
        "route": incident.get("route"),
        "analytical": bool(incident.get("analytical")),
        "response": incident.get("response"),
    }
    wait = 0
    if incident.get("at"):
        wait = max(0, int((now_local() - parse_iso(incident["at"])).total_seconds() // 60))
    weight = {"critica": 100, "alta": 70, "media": 40, "baixa": 15}.get(priority, 40)
    if status == "aberto":
        weight += 15 + min(30, wait // 2)
    out["wait_min"] = wait
    out["queue_score"] = weight
    out["playbook"] = {
        "sinistro": [
            "Despachar equipe compatível",
            "Ver câmera e radar próximos",
            "Avaliar o bloqueio da faixa",
            "Isolar a área",
            "Acompanhar o desvio",
            "Liberar a via",
            "Encerrar e conferir o tempo",
        ],
        "congestionamento": ["Confirmar o ponto", "Desviar o fluxo", "Posicionar equipe", "Liberar quando normalizar"],
        "estacionamento": ["Confirmar a irregularidade", "Orientar o condutor", "Registrar e encerrar"],
    }.get(incident.get("kind"), ["Registrar", "Despachar se necessário", "Encerrar"])
    if status == "aberto":
        out["nearby"] = nearest_agents(data, incident)
    else:
        out["nearby"] = []
    return out


def _trend(item: dict) -> str:
    mean = item.get("mean") or 0
    recent = item.get("recent") or 0
    if mean and recent > mean * 1.15:
        return "subindo"
    if mean and recent < mean * 0.85:
        return "caindo"
    return "estável"


def _region_state(item: dict, opens: list[dict]) -> tuple[str, str]:
    if any(priority_of(inc) == "critica" and inc["status"] in OPEN_INCIDENT for inc in opens):
        return "critica", "Crítica"
    if item.get("ipo", 0) >= 75:
        return "critica", "Crítica"
    if item.get("ipo", 0) >= 30 or item.get("sensors_down", 0) >= 1 or len(opens) >= 3:
        return "atencao", "Atenção"
    return "normal", "Normal"


def region_board(data: dict, lives: list[dict]) -> list[dict[str, Any]]:
    board = []
    for item in lives:
        region = item["region"]
        opens = [inc for inc in data["incidents"] if inc.get("region") == region and inc.get("status") in OPEN_INCIDENT]
        free = [agent for agent in data["agents"] if agent.get("region") == region and duty_of(agent) == "disponivel"]
        down = [eq for eq in data["equipment"] if eq.get("region") == region and eq.get("status") in UNAVAILABLE]
        cameras = [eq for eq in data["equipment"] if eq.get("region") == region and eq.get("type") == "camera" and eq.get("status") == "operacional"]
        nearest = None
        for agent in data["agents"]:
            if duty_of(agent) != "disponivel" or agent.get("signal_hold"):
                continue
            km = _km(agent["lat"], agent["lng"], item["lat"], item["lng"])
            if nearest is None or km < nearest:
                nearest = km
        eta = _eta(nearest) if nearest is not None else 99
        if eta <= 5:
            cover = "até 5 min"
        elif eta <= 10:
            cover = "até 10 min"
        elif eta <= 15:
            cover = "até 15 min"
        else:
            cover = "sem cobertura em 15 min"
        blind = eta > 15 or not cameras
        state, state_label = _region_state(item, opens)
        board.append({
            "id": region,
            "region": region,
            "lat": item["lat"],
            "lng": item["lng"],
            "city": item["city"],
            "ipo": item["ipo"],
            "level": item["level"],
            "label": item["level_label"],
            "agents_active": item["have"],
            "agents_need": item["need"],
            "gap": item["gap"],
            "sensors_down": item["sensors_down"],
            "sensors_total": item["sensors_total"],
            "state": state,
            "state_label": state_label,
            "incidents_open": len(opens),
            "agents_free": len(free),
            "equipment_down": len(down),
            "trend": _trend(item),
            "cover": cover,
            "cover_min": eta,
            "blind": blind,
            "visibility": "baixa" if not cameras else "parcial" if blind else "boa",
            "capacity": "insuficiente" if len(opens) > max(1, len(free)) else "equilibrada" if len(opens) else "excedente",
        })
    return board


def operational_now(data: dict, board: list[dict]) -> dict[str, Any]:
    incidents = data["incidents"]
    critical = [inc for inc in incidents if inc.get("status") == "aberto" and priority_of(inc) == "critica"]
    in_service = [inc for inc in incidents if inc.get("status") in ("em_deslocamento", "no_local", "em_atendimento")]
    free = [agent for agent in data["agents"] if duty_of(agent) == "disponivel"]
    busy = [agent for agent in data["agents"] if agent.get("mission")]
    down = sum(1 for eq in data["equipment"] if eq.get("status") in UNAVAILABLE)
    watch = [item for item in board if item["state"] != "normal"]
    return {
        "critical": len(critical),
        "in_service": len(in_service),
        "agents_free": len(free),
        "agents_busy": len(busy),
        "equipment_down": down,
        "regions_watch": len(watch),
        "regions_watch_names": [item["region"] for item in watch],
    }


def operational_health(data: dict, moment: datetime, index: dict, board: list[dict]) -> dict[str, Any]:
    stats = kpis(data)
    lives = index["regions"]
    calm = 100 - (sum(item["ipo"] for item in lives) / len(lives))
    on_shift = [agent for agent in data["agents"] if agent.get("shift") == shift_of(moment.hour)]
    free = [agent for agent in on_shift if duty_of(agent) == "disponivel"]
    coverage = 100 * len(free) / max(1, len(on_shift))
    unassigned = sum(1 for inc in data["incidents"] if inc.get("status") == "aberto" and priority_of(inc) == "critica")
    critical_regions = sum(1 for item in board if item["state"] == "critica")
    value = 0.5 * stats["availability_pct"] + 0.3 * calm + 0.2 * coverage
    value -= 8 * unassigned
    value -= 3 * critical_regions
    value = int(round(max(0, min(100, value))))
    if value >= 85:
        band, label = "normal", "Normal"
    elif value >= 70:
        band, label = "atencao", "Atenção"
    else:
        band, label = "critica", "Crítica"
    parts = [
        f"disponibilidade dos equipamentos {fmt_num(stats['availability_pct'])}%",
        f"calma das regiões {round(calm)}%",
        f"agentes livres no turno {round(coverage)}%",
    ]
    if unassigned:
        parts.append(f"{unassigned} ocorrência crítica sem equipe")
    if critical_regions:
        parts.append(f"{critical_regions} região em estado crítico")
    return {
        "value": value,
        "band": band,
        "label": label,
        "basis": "Saúde operacional: " + "; ".join(parts) + ".",
    }


def attention_queue(data: dict, moment: datetime, alerts: list[dict], preview: dict) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for incident in data["incidents"]:
        if incident.get("status") == "aberto" and priority_of(incident) in ("critica", "alta"):
            items.append({
                "id": f"att-{incident['id']}",
                "rank": 0 if priority_of(incident) == "critica" else 1,
                "title": incident["title"],
                "where": incident.get("street") or incident.get("region"),
                "why": "Ocorrência crítica sem equipe" if priority_of(incident) == "critica" else "Ocorrência de alta prioridade sem equipe",
                "action": "Despachar equipe",
                "action_id": "open",
                "target_type": "incident",
                "target_id": incident["id"],
            })
    broken = [eq for eq in data["equipment"] if eq["status"] in ("furtado", "mau_funcionamento")]
    broken.sort(key=lambda eq: eq["status"] != "furtado")
    for eq in broken[:2]:
            items.append({
                "id": f"att-{eq['id']}",
                "rank": 2,
                "title": f"{eq['serial']} fora de operação",
                "where": f"{eq['street']}, {eq['region']}",
                "why": "Equipamento indisponível" if eq["status"] == "mau_funcionamento" else "Equipamento furtado",
                "action": "Abrir ficha",
                "action_id": "open",
                "target_type": "equipment",
                "target_id": eq["id"],
            })
    for alert in alerts:
        if alert["target_type"] == "region" and alert["id"].startswith("an-"):
            items.append({
                "id": alert["id"],
                "rank": 3,
                "title": alert["title"],
                "where": alert["region"],
                "why": "Comportamento fora do padrão desta hora",
                "action": "Ver região",
                "action_id": "open",
                "target_type": "region",
                "target_id": alert["region"],
            })
            break
    upcoming = [
        eq for eq in data["equipment"]
        if maintenance_flag(eq, moment.date()) in ("proxima", "atrasada", "imediata") and eq["status"] == "operacional"
    ]
    if upcoming:
        eq = upcoming[0]
        items.append({
            "id": f"mant-{eq['id']}",
            "rank": 4,
            "title": f"Manutenção de {eq['serial']}",
            "where": eq["street"],
            "why": f"Próxima data {eq.get('next_maintenance') or 'não informada'}",
            "action": "Abrir ficha",
            "action_id": "open",
            "target_type": "equipment",
            "target_id": eq["id"],
        })
    top = next((rec for rec in preview.get("recommendations", []) if rec.get("scope") == "dia"), None)
    if top:
        items.append({
            "id": top["id"],
            "rank": 5,
            "title": top["title"],
            "where": "Previsão do dia seguinte",
            "why": "Janela em que a região pede reforço",
            "action": "Ver previsão",
            "action_id": "forecast",
            "target_type": "forecast",
            "target_id": top["id"],
            "region": top.get("region"),
            "hour": top.get("hour"),
        })
    items.sort(key=lambda item: (item["rank"], item["title"]))
    return items[:6]


def recent_changes(data: dict, moment: datetime) -> dict[str, Any]:
    since = moment - timedelta(hours=2)
    fresh = [inc for inc in data["incidents"] if parse_iso(inc["at"]) >= since]
    feed = [item for item in data["feed"] if parse_iso(item["at"]) >= since]
    return {
        "since": iso(since),
        "label": "Nas últimas 2 horas",
        "new_incidents": len(fresh),
        "critical_notes": sum(1 for item in feed if item["level"] == "critico"),
        "updates": len(feed),
        "lines": [{"at": item["at"], "text": item["text"], "level": item["level"]} for item in feed[:6]],
    }


def capture_frame(data: dict, moment: datetime) -> dict[str, Any]:
    return {
        "at": iso(moment),
        "agents": [
            {
                "id": agent["id"],
                "lat": agent["lat"],
                "lng": agent["lng"],
                "status": agent["status"],
                "mission": agent.get("mission"),
            }
            for agent in data["agents"]
        ],
        "incidents": [
            {
                "id": inc["id"],
                "lat": inc["lat"],
                "lng": inc["lng"],
                "status": inc["status"],
                "priority": priority_of(inc),
                "title": inc["title"],
                "region": inc["region"],
            }
            for inc in data["incidents"]
            if inc.get("status") in OPEN_INCIDENT and parse_iso(inc["at"]) <= moment
        ],
        "equipment": [
            {"id": eq["id"], "lat": eq["lat"], "lng": eq["lng"], "status": eq["status"], "type": eq["type"]}
            for eq in data["equipment"]
        ],
    }


def replay_view(data: dict, at: str | None) -> dict[str, Any]:
    frames = data.get("replay") or []
    index = [{"at": frame["at"]} for frame in frames]
    chosen = frames[-1] if frames else None
    if at and frames:
        target = parse_iso(at)
        chosen = min(frames, key=lambda frame: abs((parse_iso(frame["at"]) - target).total_seconds()))
    return {"frames": index, "frame": chosen}


def dispatch(data: dict, incident_id: str, agent_id: str | None, moment: datetime) -> dict[str, Any]:
    if not agent_id:
        raise Invalid("Escolha a equipe.")
    incident = _must(data["incidents"], incident_id, "Ocorrência")
    if incident.get("status") in ("encerrada", "ciencia"):
        raise Invalid("Esta ocorrência já foi encerrada.")
    agent = _must(data["agents"], str(agent_id), "Agente")
    if agent.get("status") in ("fora_de_servico", "em_pausa"):
        raise Invalid(f"{agent['name']} não está disponível para despacho.")
    if agent.get("mission") and agent["mission"].get("incident_id") != incident_id:
        raise Invalid(f"{agent['name']} já está em outra missão.")
    previous = incident.get("assigned_agent_id")
    if previous and previous != agent["id"]:
        _release_agent(data, previous, moment, keep_feed=False)
    km = _km(agent["lat"], agent["lng"], incident["lat"], incident["lng"])
    route = {
        "origin": [agent["lat"], agent["lng"]],
        "target": [incident["lat"], incident["lng"]],
        "distance_km": round(km, 1),
        "eta_min": _eta(km),
        "label": f"{agent['team']} → ocorrência {incident_number(incident)}",
    }
    incident["assigned_agent_id"] = agent["id"]
    incident["status"] = "em_deslocamento"
    incident["route"] = route
    incident["eta_planned"] = route["eta_min"]
    incident.setdefault("marks", {})
    incident["marks"].setdefault("opened", incident.get("at"))
    incident["marks"]["dispatched"] = iso(moment)
    if not incident.get("timeline"):
        _log_incident(incident, "Ocorrência registrada.", parse_iso(incident["at"]))
    _log_incident(incident, f"{agent['team']} despachada: {agent['name']}.", moment)
    agent["mission"] = {"incident_id": incident["id"], "phase": "deslocamento", "started_at": iso(moment)}
    agent["route"] = route
    agent["status"] = "em_deslocamento"
    agent["region"] = incident["region"]
    agent["updated_at"] = iso(moment)
    agent["last_seen"] = iso(moment)
    push_feed(
        data, "atencao",
        f"{agent['name']} ({agent['team']}) despachado para a ocorrência {incident_number(incident)}.",
        incident["region"], moment,
    )
    return {
        "message": f"{agent['team']} a caminho da ocorrência {incident_number(incident)}. ETA {_eta(km)} min.",
        "focus": {"kind": "incident", "id": incident["id"]},
    }


def advance(data: dict, incident_id: str, step: str | None, note: str, moment: datetime) -> dict[str, Any]:
    incident = _must(data["incidents"], incident_id, "Ocorrência")
    agent = next((item for item in data["agents"] if item["id"] == incident.get("assigned_agent_id")), None)
    if not agent or not agent.get("mission"):
        raise Invalid("Não há equipe atribuída a esta ocorrência.")
    note = _clean_text(note, "o registro", 400, required=False)
    phase = agent["mission"].get("phase")
    if step == "chegou":
        if phase != "deslocamento":
            raise Invalid("A equipe já registrou a chegada.")
        incident["status"] = "no_local"
        agent["mission"]["phase"] = "no_local"
        agent["status"] = "em_atividade"
        agent["lat"], agent["lng"] = incident["lat"], incident["lng"]
        incident.setdefault("marks", {})["arrived"] = iso(moment)
        _log_incident(incident, f"{agent['name']} chegou ao local.", moment)
        text = f"{agent['name']} no local da ocorrência {incident_number(incident)}."
    elif step == "iniciar":
        if phase not in ("no_local", "deslocamento"):
            raise Invalid("O atendimento já foi iniciado.")
        incident["status"] = "em_atendimento"
        agent["mission"]["phase"] = "atendimento"
        agent["status"] = "em_atividade"
        incident.setdefault("marks", {})["started"] = iso(moment)
        detail = f" Atendimento: {note}" if note else ""
        _log_incident(incident, f"Atendimento iniciado por {agent['name']}.{detail}", moment)
        text = f"Atendimento da ocorrência {incident_number(incident)} em andamento."
    elif step == "finalizar":
        incident["status"] = "encerrada"
        marks = incident.setdefault("marks", {})
        marks.setdefault("opened", incident.get("at"))
        marks["closed"] = iso(moment)
        def _gap(start, end):
            if not start or not end:
                return None
            return max(0, int((parse_iso(end) - parse_iso(start)).total_seconds() // 60))
        travel = _gap(marks.get("dispatched"), marks.get("arrived"))
        eta = incident.get("eta_planned")
        if travel is not None and eta is not None and travel > eta + 3:
            compare = f"ETA previsto {eta} min, chegada em {travel} min. O deslocamento passou da conta."
        elif travel is not None and eta is not None:
            compare = f"ETA previsto {eta} min, chegada em {travel} min. Ficou dentro do previsto."
        else:
            compare = "Sem ETA e chegada suficientes para comparar previsto e realizado."
        incident["response"] = {
            "dispatch_min": _gap(marks.get("opened"), marks.get("dispatched")),
            "travel_min": travel,
            "service_min": _gap(marks.get("started") or marks.get("arrived"), marks["closed"]),
            "total_min": _gap(marks.get("opened"), marks["closed"]),
            "eta_min": eta,
            "compare": compare,
        }
        closing = f" Atendimento finalizado. {note}" if note else " Atendimento finalizado."
        _log_incident(incident, f"{agent['name']} encerrou a ocorrência.{closing}", moment)
        __import__("ops_vehicles").release(data, incident.get("assigned_vehicle_id"), moment)
        incident["assigned_vehicle_id"] = None
        _release_agent(data, agent["id"], moment, keep_feed=False)
        incident["route"] = None
        text = f"Ocorrência {incident_number(incident)} encerrada."
    else:
        raise Invalid("Passo de atendimento desconhecido.")
    push_feed(data, "info", text, incident["region"], moment)
    return {"message": text, "focus": {"kind": "incident", "id": incident["id"]}}


def _nearest_neighbor(agent: dict, points: list[dict]) -> list[dict]:
    rest = [dict(point) for point in points]
    ordered = []
    lat, lng = agent["lat"], agent["lng"]
    while rest:
        rest.sort(key=lambda point: _haversine(lat, lng, point["lat"], point["lng"]))
        nxt = rest.pop(0)
        ordered.append(nxt)
        lat, lng = nxt["lat"], nxt["lng"]
    return ordered


def plan_route(data: dict, payload: dict, moment: datetime) -> dict[str, Any]:
    agent = _must(data["agents"], payload.get("agent_id"), "Agente")
    raw = payload.get("stops") or []
    if not isinstance(raw, list) or not raw:
        raise Invalid("Selecione ao menos um ponto.")
    if len(raw) > 8:
        raise Invalid("A rota aceita até 8 pontos.")
    points = []
    for stop in raw:
        if not isinstance(stop, dict):
            raise Invalid("Ponto inválido.")
        kind = stop.get("kind")
        if kind == "equipment":
            eq = _must(data["equipment"], stop.get("id"), "Equipamento")
            points.append({
                "kind": "equipment", "id": eq["id"],
                "label": f"{eq['serial']} · {eq['street']}",
                "lat": eq["lat"], "lng": eq["lng"], "region": eq["region"],
            })
        elif kind == "incident":
            inc = _must(data["incidents"], stop.get("id"), "Ocorrência")
            points.append({
                "kind": "incident", "id": inc["id"],
                "label": f"Ocorrência {incident_number(inc)} · {inc.get('street') or inc['region']}",
                "lat": inc["lat"], "lng": inc["lng"], "region": inc["region"],
            })
        else:
            raise Invalid("Ponto desconhecido.")
    ordered = points if payload.get("keep_order") else _nearest_neighbor(agent, points)
    driven = __import__("ops_vehicles").drive_plan(agent, ordered)
    plan = {
        "stops": ordered,
        "distance_km": driven["distance_km"],
        "duration_min": driven["duration_min"],
        "polyline": driven["polyline"],
        "road": True,
        "created_at": iso(moment),
        "status": "aprovada" if payload.get("status") == "aprovada" else "planejada",
        "origin": agent.get("region"),
        "traffic_note": driven.get("note") or "Tempo estimado pelas vias do mapa. Não inclui trânsito ao vivo.",
    }
    agent["plan"] = plan
    agent["updated_at"] = iso(moment)
    push_feed(
        data, "info",
        f"Rota de {agent['name']}: {len(ordered)} pontos, {fmt_num(plan['distance_km'])} km.",
        agent["region"], moment,
    )
    return {
        "message": f"Rota de {agent['name']} com {len(ordered)} pontos. {fmt_num(plan['distance_km'])} km, cerca de {plan['duration_min']} min.",
        "focus": {"kind": "agent", "id": agent["id"]},
        "plan": plan,
    }


def clear_plan(data: dict, agent_id: str, moment: datetime) -> dict[str, Any]:
    agent = _must(data["agents"], agent_id, "Agente")
    agent["plan"] = None
    agent["updated_at"] = iso(moment)
    return {"message": f"Rota de {agent['name']} removida.", "focus": {"kind": "agent", "id": agent["id"]}}


def _seed_operations(data: dict, moment: datetime) -> None:
    hero = {
        "id": _next_id(data, "incident", "OC"),
        "kind": "sinistro",
        "severity": "alta",
        "priority": "critica",
        "status": "aberto",
        "analytical": False,
        "title": "Colisão com faixa bloqueada na Sampaio Vidal",
        "detail": "Dois veículos. Uma faixa da Avenida Sampaio Vidal segue fechada no sentido centro. Sem equipe no local.",
        "region": "Sampaio Vidal",
        "street": "Avenida Sampaio Vidal",
        "reference": "em frente ao terminal",
        "lat": -22.2174,
        "lng": -49.9652,
        "at": iso(moment - timedelta(minutes=6)),
        "assigned_agent_id": None,
        "timeline": [{
            "at": iso(moment - timedelta(minutes=6)),
            "text": "Ocorrência registrada a partir do radar e da fila na avenida.",
        }],
    }
    low = {
        "id": _next_id(data, "incident", "OC"),
        "kind": "estacionamento",
        "severity": "baixa",
        "priority": "baixa",
        "status": "aberto",
        "analytical": False,
        "title": "Veículo parado em fila dupla na Rua São Luiz",
        "detail": "Registro de baixa prioridade. Não bloqueia o corredor.",
        "region": "Centro Marília",
        "street": "Rua São Luiz",
        "reference": "número 181",
        "lat": -22.2149,
        "lng": -49.9456,
        "at": iso(moment - timedelta(minutes=18)),
        "assigned_agent_id": None,
        "timeline": [{"at": iso(moment - timedelta(minutes=18)), "text": "Ocorrência registrada pelo agente de campo."}],
    }
    closed_at = moment - timedelta(minutes=70)
    done = {
        "id": _next_id(data, "incident", "OC"),
        "kind": "sinistro",
        "severity": "media",
        "priority": "media",
        "status": "encerrada",
        "analytical": False,
        "title": "Veículo com pane na Avenida Rio Branco",
        "detail": "Encerrada. A faixa foi liberada.",
        "region": "Centro Marília",
        "street": "Avenida Rio Branco",
        "reference": "em frente à praça",
        "lat": -22.2128,
        "lng": -49.9472,
        "at": iso(closed_at),
        "assigned_agent_id": None,
        "timeline": [
            {"at": iso(closed_at), "text": "Ocorrência registrada."},
            {"at": iso(closed_at + timedelta(minutes=3)), "text": "Equipe Centro despachada."},
            {"at": iso(closed_at + timedelta(minutes=11)), "text": "Equipe chegou."},
            {"at": iso(closed_at + timedelta(minutes=22)), "text": "Atendimento finalizado. Via liberada."},
        ],
    }
    data["incidents"].insert(0, hero)
    data["incidents"].append(low)
    data["incidents"].append(done)
    push_feed(data, "critico", "Colisão com faixa bloqueada na Sampaio Vidal. Sem equipe atribuída.", "Sampaio Vidal", moment - timedelta(minutes=6))
    ghost = next((agent for agent in data["agents"] if agent["base_region"] == "Cândido Mota" and agent["status"] == "em_atividade"), None)
    if ghost:
        ghost["signal_hold"] = True
        ghost["last_seen"] = iso(moment - timedelta(minutes=27))
    stories = {
        "RAD-SAMPAIO": [
            (moment - timedelta(days=20), "Revisão periódica concluída. Radar voltou a operacional."),
            (moment - timedelta(minutes=50), "Situação alterada para mau funcionamento. Manutenção imediata."),
        ],
        "CAM-XAVIER": [
            (moment - timedelta(days=12), "Câmera operacional na Rua Paraná."),
            (moment - timedelta(hours=5), "Situação alterada para furtado. Ponto sem imagem."),
        ],
        "BAL-MOTA": [
            (moment - timedelta(days=8), "Aferição periódica registrada."),
            (moment - timedelta(minutes=30), "Situação alterada para mau funcionamento. Balança parou de aferir."),
        ],
        "CAM-FRAGATA": [
            (moment - timedelta(days=40), "Instalação revisada na Fragata."),
            (moment - timedelta(days=2), "Manutenção periódica venceu e a câmera segue no ar."),
        ],
    }
    for eq in data["equipment"]:
        events = stories.get(eq["serial"])
        if not events:
            continue
        eq["history"] = [{"at": iso(when), "text": text} for when, text in events]
    frames = []
    for minutes in (120, 90, 60, 30, 0):
        when = moment - timedelta(minutes=minutes)
        frame = capture_frame(data, when)
        if minutes:
            by_id = {agent["id"]: agent for agent in data["agents"]}
            by_eq = {eq["id"]: eq for eq in data["equipment"]}
            weight = 1 - minutes / 150
            for item in frame["agents"]:
                src = by_id[item["id"]]
                item["lat"] = round(src["base_lat"] + (src["lat"] - src["base_lat"]) * weight, 6)
                item["lng"] = round(src["base_lng"] + (src["lng"] - src["base_lng"]) * weight, 6)
                item["mission"] = None
                if src["status"] != "fora_de_servico":
                    item["status"] = "em_atividade"
            for item in frame["equipment"]:
                serial = by_eq[item["id"]]["serial"]
                if serial == "RAD-SAMPAIO" and minutes >= 55:
                    item["status"] = "operacional"
                if serial == "BAL-MOTA" and minutes >= 40:
                    item["status"] = "operacional"
        frames.append(frame)
    data["replay"] = frames


def self_check() -> None:
    moment = datetime(2026, 10, 20, 18, 0, tzinfo=TZ)
    assert moment.weekday() == 1, moment.weekday()
    tue = {region: lambda_of(region, 1, 18) for region in REGIONS}
    sat = {region: lambda_of(region, 5, 18) for region in REGIONS}
    assert max(tue, key=tue.get) in {"Sampaio Vidal", "Fragata", "Centro Marília"}, tue
    assert max(sat, key=sat.get) in {"Centro Assis", "Vila Xavier", "Alto Cafezal"}, sat

    data = build_demo(moment)
    serials = [eq["serial"] for eq in data["equipment"]]
    assert len(serials) == len(set(serials))
    statuses = {eq["status"] for eq in data["equipment"]}
    for key, _ in EQUIPMENT_STATUSES:
        assert key in statuses, key
    assert any(agent["status"] == "em_pausa" for agent in data["agents"])
    assert any(agent["status"] == "em_atividade" for agent in data["agents"])

    for eq in data["equipment"]:
        clean_equipment(data, eq, ignore=eq["id"])

    found = anomalies(data, moment)
    assert any(item["region"] == "Sampaio Vidal" for item in found), found
    pack = bootstrap(data, moment)
    assert pack["kpis"]["total"] == len(data["equipment"])
    assert pack["kpis"]["operational"] + pack["kpis"]["unavailable"] + pack["kpis"]["not_installed"] == pack["kpis"]["total"]
    view = predictions(data, moment, date(2026, 10, 21))
    assert view["recommendations"], "sem recomendações"
    assert view["framing"]
    saturday = predictions(data, moment, date(2026, 10, 24))
    sat_regions = " ".join(rec["title"] for rec in saturday["recommendations"])
    assert any(name in sat_regions for name in ("Assis", "Xavier", "Cafezal")), sat_regions

    try:
        clean_equipment(data, {"type": "radar"})
        raise AssertionError("validação aceitou payload vazio")
    except Invalid:
        pass

    radar = next(eq for eq in data["equipment"] if eq["serial"] == "RAD-SAMPAIO")
    before = region_hour(data, "Sampaio Vidal", moment, "plan")
    radar["status"] = "operacional"
    radar["maintenance_need"] = "agendada"
    after = region_hour(data, "Sampaio Vidal", moment, "plan")
    assert after["ipo"] <= before["ipo"], (before["ipo"], after["ipo"])
    print("check ok")
    print("terça 18h", {k: round(v, 2) for k, v in tue.items()})
    print("sábado 18h", {k: round(v, 2) for k, v in sat.items()})
    print("índice", pack["city_index"]["value"], pack["city_index"]["sentence"])
    print("alertas", len(pack["alerts"]))
    for rec in view["recommendations"]:
        print("-", rec["priority"], rec["title"])
    hot = next(row for row in view["grid"] if row["region"] == "Sampaio Vidal")
    print("estreito amanhã pico", hot["peak_hour"], hot["peak_ipo"])
    print("tendência", view["trends"]["incidents"]["note"])
