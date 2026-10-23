"""Iranian mutual funds from FIPIRAN, and the network of funds and the firms behind them.

Each fund has a manager, a guarantor (liquidity provider), a custodian and an auditor. Mapping
these links shows how concentrated fund management is, which matters for systemic and
counterparty risk when one manager runs many funds.
"""

from __future__ import annotations

import networkx as nx
import pandas as pd

from .http import HttpClient

BASE = "https://fund.fipiran.ir/api/v1/fund"
ROLES = ("manager", "guarantor", "custodian", "auditor")


class FipiranClient:
    def __init__(self, http: HttpClient | None = None, base: str = BASE):
        self.http = http or HttpClient()
        self.base = base

    def funds(self) -> pd.DataFrame:
        """One row per fund: name, type, size, NAVs, returns, manager, guarantor, ...

        Uses the ``dependencygraph`` endpoint, which returns every registered fund together
        with the firms connected to it.
        """
        data = self.http.get_json(f"{self.base}/dependencygraph")
        return flatten_funds(data.get("items", []))


def flatten_funds(items) -> pd.DataFrame:
    """Turn the raw API items into one flat row per fund.

    Firms come back either as nested objects (``{"name": ..., "managerId": ...}``) or only in a
    ``temp<Role>Name`` field; both are reduced to the firm's name.
    """
    df = pd.DataFrame(items)
    for role in ROLES:
        temp = f"temp{role.capitalize()}Name"
        values = df[role] if role in df else pd.Series(None, index=df.index, dtype=object)
        names = values.map(lambda v: v.get("name") if isinstance(v, dict) else v)
        if temp in df:
            names = names.where(names.notna() & (names != ""), df[temp])
        df[role] = names
    return df


def fund_network(funds: pd.DataFrame, roles=ROLES, name_col: str = "name",
                 size_col: str | None = "netAsset") -> nx.Graph:
    """Bipartite graph: fund nodes linked to the firms that fill each role."""
    g = nx.Graph()
    for _, row in funds.iterrows():
        fund = row[name_col]
        size = float(row[size_col]) if size_col and pd.notna(row.get(size_col)) else 0.0
        g.add_node(fund, kind="fund", size=size)
        for role in roles:
            firm = row.get(role)
            if isinstance(firm, str) and firm.strip():
                firm = firm.strip()
                if firm not in g:
                    g.add_node(firm, kind="firm")
                if g.has_edge(fund, firm):
                    g.edges[fund, firm]["roles"].append(role)
                else:
                    g.add_edge(fund, firm, roles=[role])
    return g


def manager_concentration(funds: pd.DataFrame, role: str = "manager", size_col: str = "netAsset") -> tuple[pd.DataFrame, float]:
    """Funds and assets per firm, with each firm's market share and the Herfindahl index (0-10,000)."""
    d = funds.dropna(subset=[role])
    table = d.groupby(role).agg(funds=(role, "size"), assets=(size_col, "sum")).sort_values("assets", ascending=False)
    table["share"] = table["assets"] / table["assets"].sum()
    hhi = float((100 * table["share"]) .pow(2).sum())
    return table, hhi


def to_html(graph: nx.Graph, path: str) -> None:
    """Interactive network (needs the 'viz' extra: pip install pyvis)."""
    from pyvis.network import Network

    net = Network(height="800px", width="100%", cdn_resources="in_line")
    for node, attrs in graph.nodes(data=True):
        is_fund = attrs.get("kind") == "fund"
        net.add_node(node, label=node, color="#3182ce" if is_fund else "#dd6b20",
                     size=10 if is_fund else 10 + 3 * graph.degree(node))
    for a, b, attrs in graph.edges(data=True):
        net.add_edge(a, b, title=", ".join(attrs["roles"]))
    with open(path, "w", encoding="utf-8") as f:
        f.write(net.generate_html())
